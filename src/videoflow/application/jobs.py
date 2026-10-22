"""In-process job manager for the portable pipeline.

One process, a bounded number of workers, in-memory state. A restart loses job
history but never damages a project already written to disk.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from videoflow.adapters.llm import OpenAICompatibleLlm
from videoflow.application.audio import audio_filters
from videoflow.application.capabilities import ensure_external_allowed
from videoflow.application.images import images_dir
from videoflow.application.music import music_dir
from videoflow.application.portable import run_portable
from videoflow.application.telemetry import JobTelemetry
from videoflow.domain.config import (
    AudioEnhanceConfig,
    CaptionStyle,
    IntroOutroConfig,
    JlCutsConfig,
    ModuleEnabled,
    ModulesConfig,
    MusicConfig,
    OverlayConfig,
    ShortsConfig,
    TranscribeConfig,
    ZoomsConfig,
)
from videoflow.domain.errors import (
    JobCancelledError,
    JobNotFoundError,
    JobQueueFullError,
    ProjectStateError,
    VideoFlowError,
)
from videoflow.domain.state import ManualOverride, ProjectState, Sentence
from videoflow.exporters.fcpxml import Dialect

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
TERMINAL: frozenset[str] = frozenset({"succeeded", "failed", "cancelled"})
Runner = Callable[..., Any]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@dataclass
class Job:
    source: Path
    output: Path
    options: dict[str, Any]
    job_id: UUID = field(default_factory=uuid4)
    status: JobStatus = "queued"
    progress: int = 0
    stage: str = "queued"
    message: str = "Waiting for a worker"
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    cancel_requested: bool = False
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    telemetry: JobTelemetry = field(default_factory=JobTelemetry)
    finalizer: Callable[[Job], None] | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": str(self.job_id),
            "status": self.status,
            "progress": self.progress,
            "stage": self.stage,
            "message": self.message,
            "source": str(self.source),
            "output": str(self.output),
            "options": self.options,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": _duration_ms(self.started_at, self.finished_at),
            "log_count": self.telemetry.log_count(),
            "stages": self.telemetry.stages(),
        }




def _string_dict(value: object, default: dict[str, str]) -> dict[str, str]:
    if isinstance(value, dict):
        return {
            str(key).strip(): str(item).strip()
            for key, item in value.items()
            if str(key).strip()
        }
    if isinstance(value, str):
        parsed: dict[str, str] = {}
        for item in value.split(","):
            key, separator, item_value = item.partition("=")
            if separator and key.strip() and item_value.strip():
                parsed[key.strip()] = item_value.strip()
        return parsed or default
    return default


def _string_list(value: object, default: list[str]) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return default


def _shorts_config(options: dict[str, object]) -> ShortsConfig:
    count = max(1, int(options.get("shorts_count", 3)))
    requested_min = options.get("shorts_min_count")
    minimum = min(3, count) if requested_min is None else max(1, min(int(requested_min), count))
    return ShortsConfig(
        target_duration_min_sec=int(options.get("shorts_min_sec", 30)),
        target_duration_max_sec=int(options.get("shorts_max_sec", 60)),
        min_clips=minimum,
        max_clips_to_generate=count,
        selection_mode=str(options.get("shorts_selection_mode", "auto")),  # type: ignore[arg-type]
        prompt=str(options.get("shorts_prompt", "")),
        reprompt=str(options.get("shorts_reprompt", "")),
        prompt_mode=str(options.get("shorts_prompt_mode", "replace")),  # type: ignore[arg-type]
        hook_mode=str(options.get("shorts_hook_mode", "off")),  # type: ignore[arg-type]
        reframe_mode=str(options.get("shorts_reframe_mode", "center_crop_9_16")),  # type: ignore[arg-type]
        audio_energy_boost=bool(options.get("shorts_audio_energy_boost", False)),
        scene_change_boost=bool(options.get("shorts_scene_change_boost", False)),
        remove_fillers=bool(options.get("shorts_remove_fillers", False)),
        filler_words=_string_list(
            options.get("shorts_filler_words"),
            ["hum", "hmm", "uh", "um", "ah", "eh", "erm", "er"],
        ),
        aspect_ratio=str(options.get("shorts_aspect", "9:16")),  # type: ignore[arg-type]
        resolution=int(options.get("shorts_resolution", 1080)),  # type: ignore[arg-type]
        source_start_sec=float(options.get("shorts_source_start_sec", 0.0)),
        source_end_sec=(
            float(options["shorts_source_end_sec"])
            if options.get("shorts_source_end_sec") is not None
            else None
        ),
        burn_subtitles=bool(options.get("shorts_subtitles", True)),
        caption_style=_caption_style(options),
    )


def _caption_style(options: dict[str, object]) -> CaptionStyle:
    return CaptionStyle(
        font_family=str(options.get("caption_font_family", "Arial")),
        font_size=int(options.get("caption_font_size", 72)),
        font_weight=str(options.get("caption_font_weight", "bold")),  # type: ignore[arg-type]
        italic=bool(options.get("caption_italic", False)),
        uppercase=bool(options.get("caption_uppercase", False)),
        primary_color=str(options.get("caption_primary_color", "#FFFFFF")),
        highlight_color=str(options.get("caption_highlight_color", "#FFD400")),
        outline_color=str(options.get("caption_outline_color", "#000000")),
        outline_width=int(options.get("caption_outline_width", 4)),
        shadow_color=str(options.get("caption_shadow_color", "#000000")),
        shadow_offset=int(options.get("caption_shadow_offset", 2)),
        shadow_opacity=float(options.get("caption_shadow_opacity", 0.6)),
        background_color=str(options.get("caption_background_color", "#000000")),
        background_opacity=float(options.get("caption_background_opacity", 0.0)),
        background_padding=int(options.get("caption_background_padding", 0)),
        alignment=int(options.get("caption_alignment", 2)),
        position_x=float(options.get("caption_position_x", 0.5)),
        position_y=float(options.get("caption_position_y", 0.78)),
        max_width=float(options.get("caption_max_width", 0.9)),
        animation=str(options.get("caption_animation", "none")),  # type: ignore[arg-type]
        word_timing=str(options.get("caption_word_timing", "engine")),  # type: ignore[arg-type]
        censor_enabled=bool(options.get("caption_censor_enabled", False)),
        censor_words=_string_list(
            options.get("caption_censor_words"),
            ["porra", "merda", "caralho", "foda", "fuck", "shit", "bitch", "asshole"],
        ),
        censor_replacement=str(options.get("caption_censor_replacement", "***")),
        keyword_highlight_enabled=bool(options.get("caption_keyword_highlight_enabled", False)),
        keyword_color=str(options.get("caption_keyword_color", "#00E5FF")),
        keyword_words=_string_list(options.get("caption_keyword_words"), []),
        emoji_enabled=bool(options.get("caption_emoji_enabled", False)),
        emoji_map=_string_dict(options.get("caption_emoji_map"), {}),
        brand_vocabulary=_string_dict(options.get("caption_brand_vocabulary"), {}),
    )

class JobManager:
    def __init__(
        self,
        runner: Runner = run_portable,
        *,
        max_active: int = 2,
        history: int = 50,
        store_dir: Path | None = None,
    ) -> None:
        self._runner = runner
        self._max_active = max_active
        self._history = history
        self._store_dir = Path(store_dir).expanduser() if store_dir is not None else None
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        if self._store_dir is not None:
            self._load_jobs()

    def start(
        self,
        source: Path,
        output: Path,
        options: dict[str, Any] | None = None,
        *,
        finalizer: Callable[[Job], None] | None = None,
    ) -> Job:
        with self._lock:
            self._prune()
            active = sum(1 for job in self._jobs.values() if job.status not in TERMINAL)
            if active >= self._max_active:
                raise JobQueueFullError(
                    f"{self._max_active} jobs are already active. Wait or cancel one."
                )
            job = Job(
                source=Path(source),
                output=Path(output),
                options=dict(options or {}),
                finalizer=finalizer,
            )
            self._jobs[str(job.job_id)] = job
            self._persist_job(job)
        thread = threading.Thread(
            target=self._work,
            args=(job,),
            name=f"videoflow-job-{job.job_id}",
            daemon=True,
        )
        thread.start()
        return job

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None and self._store_dir is not None:
                path = self._store_dir / f"{job_id}.json"
                if path.is_file():
                    try:
                        job = _job_from_dict(json.loads(path.read_text(encoding="utf-8")))
                    except (OSError, ValueError, KeyError, TypeError):
                        job = None
                    if job is not None:
                        self._jobs[job_id] = job
            if job is None:
                raise JobNotFoundError(f"Unknown job: {job_id}")
            return job

    def list(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)

    def cancel(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(f"Unknown job: {job_id}")
            if job.status in TERMINAL:
                return job
            job.cancel_requested = True
            if job.status == "queued":
                job.status = "cancelled"
                job.stage = "cancelled"
                job.message = "Cancelled before starting"
                job.finished_at = _now()
            else:
                job.message = "Cancellation requested"
            self._persist_job(job)
            return job

    def _work(self, job: Job) -> None:
        if job.options.get("mode") == "recipe":
            self._work_recipe(job)
            return
        with self._lock:
            job.status = "running"
            job.started_at = _now()
            job.message = "Starting"
        options = job.options
        jl = JlCutsConfig(
            enable_j_cuts=bool(options.get("jcut", True)),
            enable_l_cuts=bool(options.get("lcut", False)),
            offset_ms=int(options.get("offset_ms", 200)),
            audio_crossfade_ms=int(options.get("crossfade_ms", 20)),
            fade_in_ms=int(options.get("fade_in_ms", 20)),
            fade_out_ms=int(options.get("fade_out_ms", 20)),
            fade_curve=str(options.get("fade_curve", "logarithmic")),  # type: ignore[arg-type]
            handle_check=bool(options.get("handle_check", True)),
        )
        zooms = ZoomsConfig(
            mode=str(options.get("zoom_mode", "alternate_cuts")),  # type: ignore[arg-type]
            min_scale=float(options.get("zoom_min_scale", 1.0)),
            max_scale=float(options.get("zoom_max_scale", 1.5)),
            punch_in_scale=float(options.get("punch_in_scale", 1.15)),
            anchor_point=str(options.get("anchor_point", "upper_third")),  # type: ignore[arg-type]
            progressive_zoom=bool(options.get("progressive_zoom", False)),
            pan_direction=str(options.get("pan_direction", "none")),  # type: ignore[arg-type]
        )
        if not options.get("zooms", True):
            zooms = ZoomsConfig(
                mode="manual_rules",
                min_scale=zooms.min_scale,
                max_scale=zooms.max_scale,
                anchor_point=zooms.anchor_point,
            )
        dialect: Dialect = options.get("dialect", "1.9")
        overlay_config = OverlayConfig(
            enabled=bool(options.get("overlay_enabled", False)),
            asset=str(options.get("overlay_asset", "")),
            position=str(options.get("overlay_position", "bottom_right")),  # type: ignore[arg-type]
            margin_px=int(options.get("overlay_margin_px", 32)),
            width_ratio=float(options.get("overlay_width_ratio", 0.18)),
            opacity=float(options.get("overlay_opacity", 0.9)),
        )
        overlay_path = (
            images_dir() / overlay_config.asset
            if overlay_config.enabled and overlay_config.asset
            else None
        )
        music_config = MusicConfig(
            enabled=bool(options.get("music_enabled", False)),
            asset=str(options.get("music_asset", "")),
            volume=float(options.get("music_volume", 0.18)),
            ducking=bool(options.get("music_ducking", True)),
            fade_in_ms=int(options.get("music_fade_in_ms", 250)),
            fade_out_ms=int(options.get("music_fade_out_ms", 500)),
        )
        music_path = (
            music_dir() / music_config.asset
            if music_config.enabled and music_config.asset
            else None
        )
        intro_config = IntroOutroConfig(
            intro_enabled=bool(options.get("intro_enabled", False)),
            intro_asset=str(options.get("intro_asset", "")),
            intro_duration_sec=float(options.get("intro_duration_sec", 2.0)),
            outro_enabled=bool(options.get("outro_enabled", False)),
            outro_asset=str(options.get("outro_asset", "")),
            outro_duration_sec=float(options.get("outro_duration_sec", 2.0)),
        )
        intro_path = (
            images_dir() / intro_config.intro_asset
            if intro_config.intro_enabled and intro_config.intro_asset
            else None
        )
        outro_path = (
            images_dir() / intro_config.outro_asset
            if intro_config.outro_enabled and intro_config.outro_asset
            else None
        )
        audio_config = AudioEnhanceConfig(
            enabled=bool(options.get("audio_enhance", False)),
            highpass_hz=int(options.get("audio_highpass_hz", 80)),
            denoise=bool(options.get("audio_denoise", True)),
            denoise_db=int(options.get("audio_denoise_db", 12)),
            noise_floor_db=int(options.get("audio_noise_floor_db", -30)),
            loudnorm=bool(options.get("audio_loudnorm", True)),
            target_lufs=float(options.get("audio_target_lufs", -16.0)),
            true_peak_db=float(options.get("audio_true_peak_db", -1.5)),
        )
        transcript = options.get("transcript")
        cull = bool(options.get("cull_retakes", False))
        allow_external_services = bool(options.get("allow_external_services", False))
        allowed_external_hosts = tuple(
            str(item) for item in (options.get("allowed_external_hosts") or [])
        )
        base_url = options.get("llm_base_url") or os.environ.get("VIDEOWFLOW_LLM_BASE_URL")

        telemetry = job.telemetry

        def progress(stage: str, percent: int, message: str) -> None:
            with self._lock:
                job.stage = stage
                job.progress = percent
                job.message = message

        def log(module: str, level: str, message: str) -> None:
            telemetry.log(module, level, message)

        def should_cancel() -> bool:
            return job.cancel_requested

        try:
            transcript_sentences = _project_transcript(options.get("transcript_state"))
            shorts = bool(options.get("shorts", False))
            if base_url and (cull or shorts) and (
                transcript or transcript_sentences or bool(options.get("transcribe", False))
            ):
                ensure_external_allowed(
                    str(base_url),
                    capability="external_llm",
                    allow_external_services=allow_external_services,
                allowed_external_hosts=allowed_external_hosts,
                    allowed_hosts=allowed_external_hosts,
                )
                llm = OpenAICompatibleLlm(
                    base_url=str(base_url),
                    model=str(
                        options.get("llm_model")
                        or os.environ.get("VIDEOWFLOW_LLM_MODEL", "qwen2.5:7b-instruct")
                    ),
                    api_key=os.environ.get("VIDEOWFLOW_LLM_API_KEY"),
                )
            else:
                llm = None
            project_id = options.get("project_id")
            modules_config = options.get("modules_config")
            module_enabled = options.get("module_enabled")
            result = self._runner(
                job.source,
                job.output,
                noise_db=float(options.get("noise_db", -30.0)),
                min_silence_ms=int(options.get("min_silence_ms", 400)),
                min_speech_ms=int(options.get("min_speech_ms", 100)),
                vad_engine=str(options.get("vad_engine", "auto")),  # type: ignore[arg-type]
                speech_threshold=float(options.get("speech_threshold", 0.5)),
                speech_pad_before_ms=int(options.get("speech_pad_before_ms", 120)),
                speech_pad_after_ms=int(options.get("speech_pad_after_ms", 150)),
                jl=jl,
                zooms=zooms,
                dialect=dialect,
                progress=progress,
                should_cancel=should_cancel,
                telemetry=telemetry,
                log=log,
                targets=tuple(options.get("export_targets", ("resolve", "premiere", "kdenlive"))),
                transcript_path=Path(transcript) if transcript else None,
                cull_retakes=cull,
                llm_client=llm,
                strictness=str(options.get("strictness", "balanced")),
                retake_strategy=str(options.get("retake_strategy", "keep_last")),
                context_window=int(options.get("context_window", 15)),
                shorts=shorts,
                shorts_count=int(options.get("shorts_count", 3)),
                shorts_min_sec=int(options.get("shorts_min_sec", 30)),
                shorts_max_sec=int(options.get("shorts_max_sec", 60)),
                shorts_subtitles=bool(options.get("shorts_subtitles", True)),
                shorts_config=_shorts_config(options),
                allow_external_services=allow_external_services,
                allowed_external_hosts=allowed_external_hosts,
                overrides=[
                    ManualOverride.model_validate(item)
                    for item in options.get("overrides", [])
                ],
                transcribe=bool(options.get("transcribe", False)),
                asr_base_url=options.get("asr_base_url")
                or os.environ.get("VIDEOWFLOW_ASR_BASE_URL"),
                asr_model=str(options.get("asr_model", "whisper-1")),
                asr_language=str(options.get("asr_language", "pt")),
                whisper_model=options.get("whisper_model") or None,
                faster_whisper_model=options.get("faster_whisper_model") or None,
                transcribe_config=TranscribeConfig(
                    engine=str(options.get("whisper_engine", "auto")),  # type: ignore[arg-type]
                    model_size=str(options.get("whisper_model_size", "small")),  # type: ignore[arg-type]
                    language=str(options.get("asr_language", "pt")),  # type: ignore[arg-type]
                    device=str(options.get("whisper_device", "cpu")),  # type: ignore[arg-type]
                    compute_type=str(  # type: ignore[arg-type]
                        options.get("whisper_compute_type", "int8")
                    ),
                    vad_filter=bool(options.get("whisper_vad_filter", False)),
                ),
                transcript_sentences=transcript_sentences,
                project_id=UUID(str(project_id)) if project_id else None,
                revision=int(options.get("revision", 1)),
                modules_config=(
                    ModulesConfig.model_validate(modules_config)
                    if modules_config is not None
                    else None
                ),
                module_enabled=(
                    ModuleEnabled.model_validate(module_enabled)
                    if module_enabled is not None
                    else None
                ),
                audio_filters=tuple(audio_filters(audio_config)),
                overlay_path=overlay_path,
                overlay_position=overlay_config.position,
                overlay_margin=overlay_config.margin_px,
                overlay_width_ratio=overlay_config.width_ratio,
                overlay_opacity=overlay_config.opacity,
                music_path=music_path,
                music_volume=music_config.volume,
                music_ducking=music_config.ducking,
                music_fade_in_ms=music_config.fade_in_ms,
                music_fade_out_ms=music_config.fade_out_ms,
                intro_path=intro_path,
                outro_path=outro_path,
                intro_duration_sec=intro_config.intro_duration_sec,
                outro_duration_sec=intro_config.outro_duration_sec,
            )
            if job.finalizer is not None and not job.cancel_requested:
                job.finalizer(job)
            with self._lock:
                if job.cancel_requested:
                    job.status = "cancelled"
                    job.stage = "cancelled"
                    job.message = "Cancelled"
                else:
                    job.status = "succeeded"
                    job.progress = 100
                    job.stage = "done"
                    job.message = "Finished"
                    job.result = _result_dict(result)
        except JobCancelledError as exc:
            with self._lock:
                job.status = "cancelled"
                job.stage = "cancelled"
                job.message = str(exc)
        except VideoFlowError as exc:
            telemetry.fail_running(exc.message)
            with self._lock:
                job.status = "failed"
                job.stage = job.stage or "failed"
                job.message = exc.message
                job.error = exc.to_dict()
        except Exception as exc:  # pragma: no cover - unexpected worker failure
            traceback.print_exc()
            telemetry.fail_running(str(exc))
            with self._lock:
                job.status = "failed"
                job.stage = job.stage or "failed"
                job.message = str(exc)
                job.error = {
                    "ok": False,
                    "code": "internal_error",
                    "message": str(exc),
                }
        finally:
            with self._lock:
                job.finished_at = _now()
            _write_log(job)
            self._persist_job(job)

    def _work_recipe(self, job: Job) -> None:
        from videoflow.core.recipe import Recipe
        from videoflow.engine.runner import RecipeRunner

        with self._lock:
            job.status = "running"
            job.started_at = _now()
            job.message = "Starting recipe"

        def progress(stage: str, percent: int, message: str) -> None:
            with self._lock:
                job.stage = stage
                job.progress = percent
                job.message = message

        def log(module: str, level: str, message: str) -> None:
            job.telemetry.log(module, level, message)

        def should_cancel() -> bool:
            return job.cancel_requested

        try:
            recipe = Recipe.model_validate(job.options.get("recipe") or {})
            transcript_sentences = [
                Sentence.model_validate(item)
                for item in job.options.get("transcript_sentences", [])
            ]
            runner = RecipeRunner(recipe)
            result = runner.run(
                job.source,
                job.output,
                progress=progress,
                should_cancel=should_cancel,
                log=log,
                telemetry=job.telemetry,
                transcript_sentences=transcript_sentences,
                through=job.options.get("through"),
                resume=bool(job.options.get("resume", True)),
            )
            if job.finalizer is not None and not job.cancel_requested:
                job.finalizer(job)
            with self._lock:
                if job.cancel_requested:
                    job.status = "cancelled"
                    job.stage = "cancelled"
                    job.message = "Cancelled"
                else:
                    job.status = "succeeded"
                    job.progress = 100
                    job.stage = "done"
                    job.message = "Finished"
                    payload = result.to_dict()
                    job.result = payload
        except JobCancelledError as exc:
            job.telemetry.fail_running(exc.message)
            with self._lock:
                job.status = "cancelled"
                job.stage = "cancelled"
                job.message = str(exc)
                job.error = {
                    "ok": False,
                    "code": "job_cancelled",
                    "message": str(exc),
                }
            _write_failure(job)
        except VideoFlowError as exc:
            job.telemetry.fail_running(exc.message)
            with self._lock:
                job.status = "failed"
                job.stage = job.stage or "failed"
                job.message = exc.message
                job.error = exc.to_dict()
            _write_failure(job)
        except Exception as exc:  # pragma: no cover - unexpected worker failure
            traceback.print_exc()
            job.telemetry.fail_running(str(exc))
            with self._lock:
                job.status = "failed"
                job.stage = job.stage or "failed"
                job.message = str(exc)
                job.error = {"ok": False, "code": "internal_error", "message": str(exc)}
            _write_failure(job)
        finally:
            with self._lock:
                job.finished_at = _now()
            _write_log(job)
            _record_recipe_history(job)
            self._persist_job(job)

    def _persist_job(self, job: Job) -> None:
        if self._store_dir is None:
            return
        try:
            self._store_dir.mkdir(parents=True, exist_ok=True)
            path = self._store_dir / f"{job.job_id}.json"
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(job.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError:
            pass

    def _load_jobs(self) -> None:
        if self._store_dir is None or not self._store_dir.is_dir():
            return
        for path in sorted(self._store_dir.glob("*.json")):
            try:
                job = _job_from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if job.status in {"queued", "running"}:
                job.status = "failed"
                job.stage = "failed"
                job.message = "Interrupted by service restart"
                job.finished_at = _now()
                job.error = {
                    "ok": False,
                    "code": "job_interrupted",
                    "message": "Interrupted by service restart",
                }
                self._persist_job(job)
            self._jobs[str(job.job_id)] = job

    def _prune(self) -> None:
        finished = [job for job in self._jobs.values() if job.status in TERMINAL]
        if len(finished) <= self._history:
            return
        finished.sort(key=lambda item: item.finished_at or "")
        for job in finished[: len(finished) - self._history]:
            self._jobs.pop(str(job.job_id), None)
            if self._store_dir is not None:
                with contextlib.suppress(OSError):
                    (self._store_dir / f"{job.job_id}.json").unlink(missing_ok=True)


def _job_from_dict(payload: dict[str, Any]) -> Job:
    job = Job(
        source=Path(str(payload.get("source", ""))),
        output=Path(str(payload.get("output", ""))),
        options=payload.get("options") if isinstance(payload.get("options"), dict) else {},
    )
    job.job_id = UUID(str(payload["job_id"])) if payload.get("job_id") else uuid4()
    job.status = str(payload.get("status", "queued"))  # type: ignore[assignment]
    job.progress = int(payload.get("progress", 0))
    job.stage = str(payload.get("stage", "queued"))
    job.message = str(payload.get("message", ""))
    job.result = payload.get("result") if isinstance(payload.get("result"), dict) else None
    job.error = payload.get("error") if isinstance(payload.get("error"), dict) else None
    job.created_at = str(payload.get("created_at", _now()))
    job.started_at = payload.get("started_at")
    job.finished_at = payload.get("finished_at")
    return job


def _record_recipe_history(job: Job) -> None:
    from videoflow.engine.history import append_run

    payload = job.result or {}
    recipe = job.options.get("recipe") if isinstance(job.options, dict) else None
    recipe_id = ""
    if isinstance(recipe, dict):
        recipe_id = str(recipe.get("id", ""))
    recipe_id = str(payload.get("recipe_id") or recipe_id)
    append_run(
        job.output,
        {
            "job_id": str(job.job_id),
            "status": job.status,
            "recipe_id": recipe_id,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "duration_ms": _duration_ms(job.started_at, job.finished_at) or 0,
            "step_runs": payload.get("step_runs", []),
            "cache_hits": payload.get("cache_hits", []),
            "cache_misses": payload.get("cache_misses", []),
            "artifacts": payload.get("artifacts", {}),
            "warnings": payload.get("warnings", []),
            "error": job.error,
            "message": job.message,
        },
    )
    if job.status == "succeeded" and os.environ.get("VIDEOWFLOW_PRUNE_AFTER_RUN", "1") != "0":
        try:
            from videoflow.engine.maintenance import prune_output

            prune_output(
                job.output,
                keep_days=int(os.environ.get("VIDEOWFLOW_KEEP_DAYS", "14")),
                keep_steps=int(os.environ.get("VIDEOWFLOW_KEEP_STEPS", "200")),
            )
        except (OSError, ValueError):
            pass


def _write_failure(job: Job) -> None:
    try:
        path = job.output / "work" / "failure.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = job.telemetry.dump().splitlines()[-200:]
        path.write_text(
            json.dumps(
                {
                    "ok": False,
                    "job_id": str(job.job_id),
                    "stage": job.stage,
                    "message": job.message,
                    "error": job.error,
                    "logs": lines,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _duration_ms(started_at: str | None, finished_at: str | None) -> int | None:
    if not started_at:
        return None
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(finished_at) if finished_at else datetime.now(UTC)
    except ValueError:
        return None
    return max(0, int((end - start).total_seconds() * 1000))


def _write_log(job: Job) -> None:
    try:
        if job.output.is_dir():
            (job.output / "job.log").write_text(job.telemetry.dump(), encoding="utf-8")
    except OSError:
        pass


def _project_transcript(raw: object) -> list[Sentence] | None:
    if not raw:
        return None
    path = Path(str(raw)).expanduser()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        state = ProjectState.model_validate(payload)
    except (OSError, ValueError) as exc:
        raise ProjectStateError(f"Cannot read project transcript from {path}: {exc}") from exc
    return list(state.transcript) or None


def _result_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_dict"):
        payload = result.to_dict()
        if isinstance(payload, dict):
            return payload
    if isinstance(result, dict):
        return result
    return {"ok": True, "result": str(result)}
