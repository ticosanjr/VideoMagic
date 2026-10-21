"""In-process job manager for the portable pipeline.

One process, a bounded number of workers, in-memory state. A restart loses job
history but never damages a project already written to disk.
"""

from __future__ import annotations

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
from videoflow.application.capabilities import ensure_external_allowed
from videoflow.application.portable import run_portable
from videoflow.application.telemetry import JobTelemetry
from videoflow.domain.config import (
    CaptionStyle,
    JlCutsConfig,
    ModuleEnabled,
    ModulesConfig,
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
        aspect_ratio=str(options.get("shorts_aspect", "9:16")),  # type: ignore[arg-type]
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
    )

class JobManager:
    def __init__(
        self,
        runner: Runner = run_portable,
        *,
        max_active: int = 2,
        history: int = 50,
    ) -> None:
        self._runner = runner
        self._max_active = max_active
        self._history = history
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

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
            return job

    def _work(self, job: Job) -> None:
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

    def _prune(self) -> None:
        finished = [job for job in self._jobs.values() if job.status in TERMINAL]
        if len(finished) <= self._history:
            return
        finished.sort(key=lambda item: item.finished_at or "")
        for job in finished[: len(finished) - self._history]:
            self._jobs.pop(str(job.job_id), None)


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
