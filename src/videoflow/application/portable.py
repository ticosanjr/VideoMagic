"""Portable pipeline: ingest, VAD, timeline, and NLE export.

This is the engine behind ``videoflow run``. It works with FFmpeg alone and
uses the bundled Silero VAD model when present, with FFmpeg silencedetect as the
fallback. Whisper and LLM features remain optional quality paths.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from videoflow import __version__
from videoflow.adapters import LlmClient
from videoflow.adapters.asr import WhisperHttpAdapter
from videoflow.adapters.faster_whisper import FasterWhisperAdapter
from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.adapters.whisper import WhisperCliAdapter
from videoflow.application.capabilities import ensure_external_allowed
from videoflow.application.export_service import export_timeline
from videoflow.application.fonts import fonts_dir
from videoflow.application.retakes import (
    cull_intervals,
    subtract_spans,
)
from videoflow.application.retakes import (
    cull_retakes as cull_transcript_retakes,
)
from videoflow.application.shorts import (
    build_ass,
    build_ass_lines,
    caption_lines,
    previous_shorts_from_report,
    select_shorts,
    sentence_events,
    short_dimensions,
    slugify,
)
from videoflow.application.telemetry import JobTelemetry
from videoflow.application.timeline_builder import build_timeline
from videoflow.application.vad import detect_speech as detect_vad
from videoflow.application.vad import pad_spans
from videoflow.domain.config import (
    JlCutsConfig,
    ModuleEnabled,
    ModulesConfig,
    ShortsConfig,
    TranscribeConfig,
    VadEngine,
    ZoomsConfig,
)
from videoflow.domain.errors import IngestError, InvalidRetakeIdsError, JobCancelledError
from videoflow.domain.state import ManualOverride, ProjectState, SampleSpan, Sentence
from videoflow.domain.timebase import Rounding
from videoflow.domain.transcript import parse_srt_file
from videoflow.exporters.common import write_text
from videoflow.exporters.fcpxml import Dialect

ProgressCallback = Callable[[str, int, str], None]
CancelCheck = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class PortableRun:
    source: Path
    output: Path
    state: ProjectState
    artifacts: dict[str, Path]
    speech_intervals: tuple[tuple[int, int], ...]
    warnings: tuple[str, ...]
    elapsed_seconds: float
    state_path: Path
    report_path: Path
    shorts: tuple[dict[str, Any], ...] = ()
    transcript_source: str = "none"
    vad_engine: str = "ffmpeg"

    def to_dict(self) -> dict[str, Any]:
        media = self.state.media_info
        return {
            "ok": True,
            "version": __version__,
            "project_id": str(self.state.project_id),
            "state_revision": self.state.revision,
            "source": str(self.source),
            "output": str(self.output),
            "media": media.model_dump(mode="json") if media else None,
            "speech_interval_count": len(self.speech_intervals),
            "video_segment_count": len(self.state.video_segments),
            "audio_segment_count": len(self.state.audio_segments),
            "transcript_sentence_count": len(self.state.transcript),
            "retake_cull_count": len(self.state.retake_culls),
            "retake_restored_count": len(self.state.retake_guard_restores),
            "manual_override_count": len(self.state.manual_overrides),
            "transcript_source": self.transcript_source,
            "vad_engine": self.vad_engine,
            "warnings": list(self.warnings),
            "artifacts": {name: str(path) for name, path in self.artifacts.items()},
            "shorts": list(self.shorts),
            "state_path": str(self.state_path),
            "report_path": str(self.report_path),
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }


def run_portable(
    source: Path,
    output: Path,
    *,
    noise_db: float = -30.0,
    min_silence_ms: int = 400,
    min_speech_ms: int = 100,
    vad_engine: VadEngine = "auto",
    speech_threshold: float = 0.5,
    speech_pad_before_ms: int = 120,
    speech_pad_after_ms: int = 150,
    jl: JlCutsConfig | None = None,
    zooms: ZoomsConfig | None = None,
    dialect: Dialect = "1.9",
    adapter: FFmpegAdapter | None = None,
    progress: ProgressCallback | None = None,
    should_cancel: CancelCheck | None = None,
    telemetry: JobTelemetry | None = None,
    log: Callable[[str, str, str], None] | None = None,
    targets: Sequence[str] = ("resolve", "premiere", "kdenlive"),
    transcript_path: Path | None = None,
    cull_retakes: bool = False,
    llm_client: LlmClient | None = None,
    strictness: str = "balanced",
    retake_strategy: str = "keep_last",
    context_window: int = 15,
    shorts: bool = False,
    shorts_count: int = 3,
    shorts_min_sec: int = 30,
    shorts_max_sec: int = 60,
    shorts_subtitles: bool = True,
    shorts_config: ShortsConfig | None = None,
    overrides: Sequence[ManualOverride] | None = None,
    transcribe: bool = False,
    asr_base_url: str | None = None,
    asr_model: str = "whisper-1",
    asr_language: str = "pt",
    whisper_model: str | Path | None = None,
    faster_whisper_model: str | Path | None = None,
    transcribe_config: TranscribeConfig | None = None,
    asr_client: Any | None = None,
    transcript_sentences: Sequence[Sentence] | None = None,
    project_id: UUID | None = None,
    revision: int = 1,
    modules_config: ModulesConfig | None = None,
    module_enabled: ModuleEnabled | None = None,
    allow_external_services: bool = False,
    allowed_external_hosts: Sequence[str] = (),
    audio_filters: Sequence[str] = (),
    overlay_path: Path | None = None,
    overlay_position: str = "bottom_right",
    overlay_margin: int = 32,
    overlay_width_ratio: float = 0.18,
    overlay_opacity: float = 0.9,
    music_path: Path | None = None,
    music_volume: float = 0.18,
    music_ducking: bool = True,
    music_fade_in_ms: int = 250,
    music_fade_out_ms: int = 500,
    intro_path: Path | None = None,
    outro_path: Path | None = None,
    intro_duration_sec: float = 2.0,
    outro_duration_sec: float = 2.0,
) -> PortableRun:
    """Run the complete portable pipeline for one source file."""

    started = time.perf_counter()
    ensure_external_allowed(
        asr_base_url,
        capability="external_asr",
        allow_external_services=allow_external_services,
        allowed_hosts=allowed_external_hosts,
    )

    def step(stage: str, percent: int, message: str) -> None:
        if progress is not None:
            progress(stage, percent, message)

    def gate() -> None:
        if should_cancel is not None and should_cancel():
            raise JobCancelledError("Job cancelled")

    def emit(module: str, level: str, message: str) -> None:
        if log is not None:
            log(module, level, message)

    @contextmanager
    def stage(stage_id: str, module: str, label: str, message: str) -> Any:
        if telemetry is not None:
            telemetry.start(stage_id, module, label, message)
        meta = {"message": message}
        try:
            yield meta
        except JobCancelledError:
            if telemetry is not None:
                telemetry.cancel(stage_id)
            raise
        except Exception as exc:
            if telemetry is not None:
                telemetry.fail(stage_id, str(exc))
            raise
        else:
            if telemetry is not None:
                telemetry.finish(stage_id, str(meta["message"]))

    source_path = Path(source).expanduser().resolve()
    output_path = Path(output).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    work = output_path / "work"
    exports = output_path / "exports"

    adapter_module = {"name": "ingest"}
    gate()
    with stage("ingest", "ingest", "Ingest", "Reading media metadata") as meta:
        step("probe", 5, "Reading media metadata")
        engine = adapter or FFmpegAdapter(
            log=lambda lvl, msg: emit(adapter_module["name"], lvl, msg)
        )
        media = engine.probe(source_path)
        gate()
        step("extract", 15, "Extracting analysis audio")
        if telemetry is not None:
            telemetry.update("ingest", 50, "Extracting analysis audio")
        wav = engine.extract_pcm(
            source_path,
            work / "source.wav",
            sample_rate=media.audio_sample_rate,
        )
        digest = engine.pcm_digest(wav)
        meta["message"] = f"PCM ready ({digest[:12]})"
        if telemetry is not None:
            telemetry.update("ingest", 90, str(meta["message"]))
        emit("ingest", "info", f"PCM SHA-256 {digest}")

    timebase = media.timebase()
    duration_samples = timebase.seconds_to_samples(
        timebase.frames_to_seconds(media.duration_frames), Rounding.NEAREST
    )
    gate()
    adapter_module["name"] = "vad"
    with stage("vad", "vad", "Voice detect", "Detecting speech and silence") as meta:
        step("vad", 35, "Detecting speech and silence")
        detection = detect_vad(
            engine,
            source_path,
            work,
            media,
            vad_engine=vad_engine,
            noise_db=noise_db,
            min_silence_ms=min_silence_ms,
            min_speech_ms=min_speech_ms,
            speech_threshold=speech_threshold,
            speech_pad_before_ms=speech_pad_before_ms,
            speech_pad_after_ms=speech_pad_after_ms,
            duration_samples=duration_samples,
            apply_pads=False,
            log=lambda level, message: emit("vad", level, message),
        )
        speech = detection.spans
        if not speech:
            raise IngestError(
                "No speech detected. Lower the noise threshold or the minimum silence duration."
            )
        meta["message"] = f"{len(speech)} speech intervals ({detection.engine})"
        emit("vad", "info", str(meta["message"]))

    transcript: list[Sentence] = []
    discard: list[int] = []
    restored: list[int] = []
    manual = list(overrides or [])
    transcript_source = "none"
    if transcript_path is not None:
        with stage(
            "transcribe", "transcribe", "Transcribe (SRT)", "Reading subtitle transcript"
        ) as meta:
            gate()
            step("transcript", 42, "Reading subtitle transcript")
            transcript = parse_srt_file(transcript_path, media.audio_sample_rate)
            transcript_source = "srt"
            meta["message"] = f"{len(transcript)} sentences from SRT"
            emit("transcribe", "info", str(meta["message"]))
    elif transcript_sentences:
        with stage(
            "transcribe",
            "transcribe",
            "Transcribe (project)",
            "Reusing the project transcript",
        ) as meta:
            gate()
            step("transcript", 42, "Reusing the project transcript")
            transcript = list(transcript_sentences)
            transcript_source = "project"
            meta["message"] = f"{len(transcript)} sentences from project state"
            emit("transcribe", "info", str(meta["message"]))
    elif transcribe:
        client = asr_client
        local_source: str | None = None
        config = transcribe_config
        if config is None and modules_config is not None:
            config = modules_config.transcribe
        if config is None:
            config = TranscribeConfig(language=asr_language)  # type: ignore[arg-type]
        language = config.language
        base_url = asr_base_url or os.environ.get("VIDEOWFLOW_ASR_BASE_URL")
        if client is None and base_url:
            client = WhisperHttpAdapter(
                base_url=base_url,
                model=asr_model,
                api_key=os.environ.get("VIDEOWFLOW_ASR_API_KEY"),
                language=language,
            )
        elif client is None:
            use_whisper_cpp = config.engine == "whisper.cpp" or (
                config.engine == "auto"
                and not FasterWhisperAdapter.available(
                    config.model_size,
                    model=faster_whisper_model,
                )
            )
            if use_whisper_cpp:
                client = WhisperCliAdapter(
                    binary=os.environ.get("VIDEOWFLOW_WHISPER_BIN"),
                    model=whisper_model or os.environ.get("VIDEOWFLOW_WHISPER_MODEL"),
                    language=language,
                    log=lambda level, message: emit("transcribe", level, message),
                )
                local_source = "whisper"
            else:
                client = FasterWhisperAdapter(
                    model=faster_whisper_model,
                    model_size=config.model_size,
                    device=config.device,
                    compute_type=config.compute_type,
                    language=language,
                    vad_filter=config.vad_filter,
                    log=lambda level, message: emit("transcribe", level, message),
                )
                local_source = "faster-whisper"
        transcript_origin = local_source or "asr"
        labels = {
            "faster-whisper": ("Transcribe (Faster-Whisper)", "Faster-Whisper"),
            "whisper": ("Transcribe (local whisper.cpp)", "local whisper.cpp"),
            "asr": ("Transcribe (ASR)", "ASR"),
        }
        label, engine_label = labels[transcript_origin]
        with stage("transcribe", "transcribe", label, "Calling speech-to-text") as meta:
            gate()
            step("transcript", 42, "Calling speech-to-text")
            source_wav = wav
            if local_source is not None:
                source_wav = engine.extract_pcm(
                    source_path, work / "transcribe.wav", sample_rate=16000
                )
            transcript = client.transcribe(source_wav, media.audio_sample_rate)
            transcript_source = transcript_origin
            if not transcript:
                raise IngestError("Speech-to-text returned no sentences.")
            meta["message"] = f"{len(transcript)} sentences from {engine_label}"
            emit("transcribe", "info", str(meta["message"]))

    if not transcript and (cull_retakes or manual):
        raise IngestError("Retake culling and overrides require a transcript.")

    if transcript and (cull_retakes or manual):
        with stage("retakes", "retakes", "Retakes", "Culling retakes") as meta:
            gate()
            step("retakes", 48, "Culling retakes")
            if cull_retakes:
                result = cull_transcript_retakes(
                    transcript,
                    client=llm_client,
                    strategy=retake_strategy,  # type: ignore[arg-type]
                    context_window=context_window,
                    strictness=strictness,
                )
                discard = list(result.discard_sentence_ids)
                restored = list(result.restored_sentence_ids)
            valid = {item.id for item in transcript}
            unknown = [item.sentence_id for item in manual if item.sentence_id not in valid]
            if unknown:
                raise InvalidRetakeIdsError(unknown)
            discarded = set(discard)
            for item in manual:
                if item.action == "discard":
                    discarded.add(item.sentence_id)
                else:
                    discarded.discard(item.sentence_id)
            discard = sorted(discarded)
            speech = subtract_spans(speech, cull_intervals(transcript, discard))
            minimum = max(1, (min_speech_ms * media.audio_sample_rate + 500) // 1000)
            speech = [(start, end) for start, end in speech if end - start >= minimum]
            if not speech:
                raise IngestError("Culling and overrides removed all speech.")
            meta["message"] = (
                f"{len(discard)} culled, {len(restored)} restored, {len(manual)} manual overrides"
            )
            emit("retakes", "info", str(meta["message"]))

    speech = pad_spans(
        speech,
        media.audio_sample_rate,
        speech_pad_before_ms,
        speech_pad_after_ms,
        duration_samples,
    )
    config_jl = jl or JlCutsConfig()
    config_zooms = zooms or ZoomsConfig()
    gate()
    step("timeline", 55, "Building the cut timeline")
    if telemetry is not None:
        telemetry.start("jl_cuts", "jl_cuts", "J/L cuts", "Building audio cuts")

    def cuts_done() -> None:
        if telemetry is not None:
            telemetry.finish("jl_cuts", "Audio cuts ready")
            telemetry.start("zooms", "zooms", "Zooms", "Building transforms")

    try:
        built = build_timeline(
            media, speech, jl=config_jl, zooms=config_zooms, on_audio_done=cuts_done
        )
    except Exception as exc:
        if telemetry is not None:
            active = telemetry.active_stage()
            if active:
                telemetry.fail(active, str(exc))
        raise
    if telemetry is not None:
        telemetry.finish("zooms", "Transforms ready")
    state = ProjectState(
        project_id=project_id or uuid4(),
        revision=max(1, revision),
        media_info=media,
        modules_config=modules_config or ModulesConfig(),
        module_enabled=module_enabled or ModuleEnabled(),
        vad_intervals=[SampleSpan(start_sample=start, end_sample=end) for start, end in speech],
        transcript=transcript,
        retake_culls=discard,
        retake_guard_restores=restored,
        manual_overrides=manual,
        video_segments=list(built.video_segments),
        audio_segments=list(built.audio_segments),
    )
    gate()
    with stage("export", "export", "Export", "Writing timelines") as meta:
        step("export", 80, "Writing FCPXML, xmeml, and OTIO")
        artifacts = export_timeline(state, exports, dialect=dialect, targets=targets)
        meta["message"] = f"{len(artifacts)} artifacts written"
        emit("export", "info", str(meta["message"]))

    short_paths: list[dict[str, Any]] = []
    warnings = list(built.warnings)
    if shorts:
        if not transcript:
            raise IngestError("Shorts require a transcript. Provide an SRT.")
        short_cfg = shorts_config or ShortsConfig(
            target_duration_min_sec=shorts_min_sec,
            target_duration_max_sec=shorts_max_sec,
            min_clips=1,
            max_clips_to_generate=max(1, shorts_count),
            burn_subtitles=shorts_subtitles,
        )
        if (
            short_cfg.target_duration_min_sec <= 0
            or short_cfg.target_duration_max_sec < short_cfg.target_duration_min_sec
        ):
            raise IngestError("Invalid shorts duration window.")
        minimum = timebase.seconds_to_samples(
            Fraction(short_cfg.target_duration_min_sec), Rounding.NEAREST
        )
        maximum = timebase.seconds_to_samples(
            Fraction(short_cfg.target_duration_max_sec), Rounding.NEAREST
        )
        cuts = cull_intervals(transcript, discard)
        kept = [item for item in transcript if item.id not in set(discard)]
        range_start = timebase.seconds_to_samples(
            Fraction(str(short_cfg.source_start_sec)), Rounding.NEAREST
        )
        range_end = (
            timebase.seconds_to_samples(
                Fraction(str(short_cfg.source_end_sec)), Rounding.NEAREST
            )
            if short_cfg.source_end_sec is not None
            else duration_samples
        )
        kept = [
            item
            for item in kept
            if item.start_sample >= range_start and item.end_sample <= range_end
        ]
        width, height = short_dimensions(short_cfg.aspect_ratio)
        previous = (
            previous_shorts_from_report(output_path / "shorts.json")
            if short_cfg.prompt_mode == "refine"
            else []
        )
        gate()
        with stage("shorts", "shorts", "Shorts", "Selecting social clips") as meta:
            selected = select_shorts(
                kept,
                min_samples=minimum,
                max_samples=maximum,
                count=max(1, short_cfg.max_clips_to_generate),
                min_clips=short_cfg.min_clips,
                selection_mode=short_cfg.selection_mode,
                sample_rate=media.audio_sample_rate,
                cuts=cuts,
                client=llm_client,
                warnings=warnings,
                prompt=short_cfg.prompt,
                reprompt=short_cfg.reprompt,
                prompt_mode=short_cfg.prompt_mode,
                previous=previous,
                hook_mode=short_cfg.hook_mode,
            )
            shorts_dir = output_path / "shorts"
            for index, clip in enumerate(selected, start=1):
                gate()
                if telemetry is not None:
                    telemetry.update(
                        "shorts",
                        int(index / max(1, len(selected)) * 90),
                        f"Rendering {index}/{len(selected)}",
                    )
                slug = slugify(clip.title, index)
                ass_path = None
                if short_cfg.burn_subtitles:
                    style = short_cfg.caption_style
                    lines = caption_lines(
                        kept,
                        clip.pieces,
                        sample_rate=media.audio_sample_rate,
                        word_timing=style.word_timing,
                        warnings=warnings,
                    )
                    if lines:
                        ass_path = shorts_dir / f"{slug}.ass"
                        write_text(
                            ass_path,
                            build_ass_lines(
                                lines,
                                style=style,
                                width=width,
                                height=height,
                            ),
                        )
                    else:
                        events = sentence_events(
                            kept, clip.pieces, sample_rate=media.audio_sample_rate
                        )
                        if events:
                            ass_path = shorts_dir / f"{slug}.ass"
                            write_text(
                                ass_path,
                                build_ass(
                                    events,
                                    style=style,
                                    width=width,
                                    height=height,
                                ),
                            )
                destination = shorts_dir / f"{slug}.mp4"
                engine.render_short(
                    source_path,
                    clip.pieces,
                    destination,
                    sample_rate=media.audio_sample_rate,
                    ass_path=ass_path,
                    width=width,
                    height=height,
                    fontsdir=str(fonts_dir()),
                    audio_filters=audio_filters,
                    overlay_path=overlay_path,
                    overlay_position=overlay_position,
                    overlay_margin=overlay_margin,
                    overlay_width_ratio=overlay_width_ratio,
                    overlay_opacity=overlay_opacity,
                    music_path=music_path,
                    music_volume=music_volume,
                    music_ducking=music_ducking,
                    music_fade_in_ms=music_fade_in_ms,
                    music_fade_out_ms=music_fade_out_ms,
                    intro_path=intro_path,
                    outro_path=outro_path,
                    intro_duration_sec=intro_duration_sec,
                    outro_duration_sec=outro_duration_sec,
                )
                entry = clip.to_dict(media.audio_sample_rate)
                entry["aspect_ratio"] = short_cfg.aspect_ratio
                entry["width"] = width
                entry["height"] = height
                entry["path"] = str(destination)
                if ass_path is not None:
                    entry["subtitles"] = str(ass_path)
                short_paths.append(entry)
            if short_paths:
                write_text(
                    output_path / "shorts.json",
                    json.dumps({"ok": True, "clips": short_paths}, indent=2) + "\n",
                )
            meta["message"] = (
                f"{len(short_paths)} shorts rendered"
                if short_paths
                else "No window reached the minimum duration"
            )
            emit("shorts", "info", str(meta["message"]))

    gate()
    step("state", 95, "Writing project state and report")
    state_path = input_state_path(output_path)
    report_path = output_path / "run.json"
    write_text(state_path, state.model_dump_json(indent=2) + "\n")
    run = PortableRun(
        source=source_path,
        output=output_path,
        state=state,
        artifacts=artifacts,
        speech_intervals=tuple(speech),
        warnings=tuple(warnings),
        elapsed_seconds=time.perf_counter() - started,
        state_path=state_path,
        report_path=report_path,
        shorts=tuple(short_paths),
        transcript_source=transcript_source,
        vad_engine=detection.engine,
    )
    report = run.to_dict()
    report["pcm_sha256"] = digest
    report["noise_db"] = noise_db
    report["min_silence_ms"] = min_silence_ms
    report["speech_threshold"] = speech_threshold
    report["speech_pad_before_ms"] = speech_pad_before_ms
    report["speech_pad_after_ms"] = speech_pad_after_ms
    write_text(report_path, _json(report))
    step("done", 100, "Finished")
    return run


def input_state_path(output: Path) -> Path:
    return output / "project_state.json"


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
