"""Model-free portable pipeline: ingest, silence detection, timeline, export.

This is the engine behind ``videoflow run``. It needs only FFmpeg/FFprobe, so a
single frozen executable is enough. Silero/Whisper/LLM remain the quality path.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from videoflow import __version__
from videoflow.adapters import LlmClient
from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.export_service import export_timeline
from videoflow.application.retakes import (
    cull_intervals,
    subtract_spans,
)
from videoflow.application.retakes import (
    cull_retakes as cull_transcript_retakes,
)
from videoflow.application.shorts import (
    build_ass,
    select_shorts,
    sentence_events,
    slugify,
)
from videoflow.application.telemetry import JobTelemetry
from videoflow.application.timeline_builder import build_timeline
from videoflow.domain.config import JlCutsConfig, ModuleEnabled, ZoomsConfig
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

    def to_dict(self) -> dict[str, Any]:
        media = self.state.media_info
        return {
            "ok": True,
            "version": __version__,
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
    overrides: Sequence[ManualOverride] | None = None,
) -> PortableRun:
    """Run the complete model-free pipeline for one source file."""

    started = time.perf_counter()

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
        speech = engine.detect_speech(
            wav,
            duration_samples=duration_samples,
            sample_rate=media.audio_sample_rate,
            noise_db=noise_db,
            min_silence_ms=min_silence_ms,
            min_speech_ms=min_speech_ms,
        )
        if not speech:
            raise IngestError(
                "No speech detected. Lower the noise threshold or the minimum silence duration."
            )
        meta["message"] = f"{len(speech)} speech intervals"
        emit("vad", "info", str(meta["message"]))

    transcript: list[Sentence] = []
    discard: list[int] = []
    restored: list[int] = []
    manual = list(overrides or [])
    if manual and transcript_path is None:
        raise IngestError("Manual overrides require a transcript. Provide an SRT.")
    if transcript_path is not None:
        with stage(
            "transcribe", "transcribe", "Transcribe (SRT)", "Reading subtitle transcript"
        ) as meta:
            gate()
            step("transcript", 42, "Reading subtitle transcript")
            transcript = parse_srt_file(transcript_path, media.audio_sample_rate)
            meta["message"] = f"{len(transcript)} sentences from SRT"
            emit("transcribe", "info", str(meta["message"]))
        if cull_retakes or manual:
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
                    f"{len(discard)} culled, {len(restored)} restored, "
                    f"{len(manual)} manual overrides"
                )
                emit("retakes", "info", str(meta["message"]))

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
        media_info=media,
        module_enabled=ModuleEnabled(),
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
        if shorts_min_sec <= 0 or shorts_max_sec < shorts_min_sec:
            raise IngestError("Invalid shorts duration window.")
        minimum = timebase.seconds_to_samples(Fraction(shorts_min_sec), Rounding.NEAREST)
        maximum = timebase.seconds_to_samples(Fraction(shorts_max_sec), Rounding.NEAREST)
        cuts = cull_intervals(transcript, discard)
        kept = [item for item in transcript if item.id not in set(discard)]
        gate()
        with stage("shorts", "shorts", "Shorts", "Selecting vertical clips") as meta:
            selected = select_shorts(
                kept,
                min_samples=minimum,
                max_samples=maximum,
                count=max(1, shorts_count),
                sample_rate=media.audio_sample_rate,
                cuts=cuts,
                client=llm_client,
                warnings=warnings,
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
                if shorts_subtitles:
                    events = sentence_events(
                        kept, clip.pieces, sample_rate=media.audio_sample_rate
                    )
                    if events:
                        ass_path = shorts_dir / f"{slug}.ass"
                        write_text(ass_path, build_ass(events))
                destination = shorts_dir / f"{slug}.mp4"
                engine.render_short(
                    source_path,
                    clip.pieces,
                    destination,
                    sample_rate=media.audio_sample_rate,
                    ass_path=ass_path,
                )
                entry = clip.to_dict(media.audio_sample_rate)
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
    )
    report = run.to_dict()
    report["pcm_sha256"] = digest
    report["noise_db"] = noise_db
    report["min_silence_ms"] = min_silence_ms
    write_text(report_path, _json(report))
    step("done", 100, "Finished")
    return run


def input_state_path(output: Path) -> Path:
    return output / "project_state.json"


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
