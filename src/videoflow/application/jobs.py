"""In-process job manager for the portable pipeline.

One process, a bounded number of workers, in-memory state. A restart loses job
history but never damages a project already written to disk.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from videoflow.application.clock import now_iso_ms as _now
from videoflow.application.job_executor import JobExecutor, JobRunPolicy, RunOutcome
from videoflow.application.telemetry import JobTelemetry
from videoflow.domain.config import (
    CaptionStyle,
    ShortsConfig,
)
from videoflow.domain.errors import (
    JobAlreadyRunningError,
    JobNotFoundError,
    JobQueueFullError,
    ProjectStateError,
)
from videoflow.domain.state import ProjectState, Sentence

JobStatus = Literal[
    "queued",
    "running",
    "waiting_approval",
    "waiting_input",
    "succeeded",
    "failed",
    "cancelled",
    "answered",
]
TERMINAL: frozenset[str] = frozenset({"succeeded", "failed", "cancelled", "answered"})
logger = logging.getLogger(__name__)


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
    pause_requested: bool = False
    priority: int = 0
    attempts: int = 0
    next_run: str = ""
    lease_expires_at: str = ""
    lease_owner: str = ""
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    telemetry: JobTelemetry = field(default_factory=JobTelemetry)
    step_progress: dict[str, int] = field(default_factory=dict)
    idempotency_key: str = ""
    project_id: str = ""
    timeline_ready: bool = False
    deleted: bool = False
    cancel_event: threading.Event = field(
        default_factory=threading.Event, repr=False, compare=False
    )
    finalizer: Callable[[Job], None] | None = field(default=None, repr=False)

    def to_dict(self, *, summary: bool = False) -> dict[str, Any]:
        options = self.options
        if summary and isinstance(options, dict):
            options = {
                key: value
                for key, value in options.items()
                if key not in {"recipe", "transcript_sentences"}
            }
        return {
            "job_id": str(self.job_id),
            "project_id": self.project_id,
            "status": self.status,
            "priority": self.priority,
            "attempts": self.attempts,
            "next_run": self.next_run,
            "lease_expires_at": self.lease_expires_at,
            "lease_owner": self.lease_owner,
            "progress": self.progress,
            "stage": self.stage,
            "message": self.message,
            "source": str(self.source),
            "output": str(self.output),
            "options": options,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": _duration_ms(self.started_at, self.finished_at),
            "step_progress": dict(self.step_progress),
            "idempotency_key": self.idempotency_key,
            "timeline_ready": self.timeline_ready,
            "log_count": self.telemetry.log_count(),
            "stages": self.telemetry.stages(),
            "interaction": (
                (self.error or {}).get("interaction")
                if self.status in {"waiting_approval", "waiting_input"}
                else None
            ),
        }


def _string_dict(value: object, default: dict[str, str]) -> dict[str, str]:
    if isinstance(value, dict):
        return {
            str(key).strip(): str(item).strip() for key, item in value.items() if str(key).strip()
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
        profile=str(options.get("shorts_profile", "default")),  # type: ignore[arg-type]
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


def _provider_value(capability: str, key: str) -> str:
    try:
        from videoflow.application.providers import first_provider

        provider = first_provider(capability)  # type: ignore[arg-type]
    except Exception:
        return ""
    return str(provider.get(key) or "") if provider else ""


class JobManager:
    def __init__(
        self,
        *,
        max_active: int = 2,
        history: int = 50,
        store_dir: Path | None = None,
        load_store: bool = True,
        recipe_runner_factory: Callable[[Any, Any], Any] | None = None,
    ) -> None:
        self._recipe_runner_factory = recipe_runner_factory
        self._max_active = max_active
        self._history = history
        self._store_dir = Path(store_dir).expanduser() if store_dir is not None else None
        self._jobs: dict[str, Job] = {}
        self._pending: list[str] = []
        self._lock = threading.Lock()
        self._retry_thread: threading.Thread | None = None
        self._executor = JobExecutor(
            self,
            write_log=_write_log,
            write_failure=_write_failure,
            record_history=_record_recipe_history,
        )
        if self._store_dir is not None and load_store:
            self._load_jobs()

    def start(
        self,
        source: Path,
        output: Path,
        options: dict[str, Any] | None = None,
        *,
        finalizer: Callable[[Job], None] | None = None,
        queue: bool = False,
        priority: int = 0,
        idempotency_key: str | None = None,
        project_id: str = "",
    ) -> Job:
        key = (idempotency_key or "").strip()
        with self._lock:
            self._prune()
            if key:
                for existing in self._jobs.values():
                    if existing.idempotency_key == key and existing.status not in TERMINAL:
                        return existing
            source_path = Path(source)
            output_path = Path(output)
            for existing in self._jobs.values():
                if (
                    existing.status in {"running", "queued", "paused"}
                    and existing.source == source_path
                    and existing.output == output_path
                ):
                    raise JobAlreadyRunningError(existing.stage or str(existing.job_id))
            active = sum(1 for job in self._jobs.values() if job.status in {"running", "queued"})
            if active >= self._max_active and not queue:
                raise JobQueueFullError(
                    f"{self._max_active} jobs are already active. Wait or cancel one."
                )
            job = Job(
                source=Path(source),
                output=Path(output),
                options=dict(options or {}),
                finalizer=finalizer,
                priority=priority,
                idempotency_key=key,
                project_id=str(project_id or (options or {}).get("project_id") or ""),
            )
            job.telemetry.job_id = str(job.job_id)
            self._jobs[str(job.job_id)] = job
            if active >= self._max_active:
                job.status = "queued"
                job.message = "Queued for the next worker slot"
                self._pending.append(str(job.job_id))
                self._persist_job(job)
            else:
                self._persist_job(job)
                self._launch(job)
        return job

    def update_result(self, job_id: str, result: dict[str, Any]) -> Job:
        """Replace a completed job result and persist it."""

        with self._lock:
            job = self._jobs.get(str(job_id))
            if job is None:
                job = self.get(str(job_id))
            job.result = dict(result)
            self._persist_job(job)
        return job

    def _ensure_retry_thread(self) -> None:
        if self._retry_thread is not None and self._retry_thread.is_alive():
            return
        self._retry_thread = threading.Thread(
            target=self._retry_loop, name="videoflow-retry", daemon=True
        )
        self._retry_thread.start()

    def _retry_loop(self) -> None:
        while True:
            time.sleep(1.0)
            with contextlib.suppress(Exception):
                self._drain_queue()

    def _schedule_retry_locked(self, job: Job) -> bool:
        max_attempts = int(job.options.get("max_attempts", 1) or 1)
        if max_attempts <= 1 or job.cancel_requested:
            return False
        if job.attempts + 1 >= max_attempts:
            return False
        job.attempts += 1
        delay = max(0.0, float(job.options.get("retry_backoff_seconds", 5) or 0))
        job.next_run = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat(timespec="seconds")
        job.status = "queued"
        job.stage = "queued"
        job.message = f"Retry {job.attempts + 1}/{max_attempts} in {delay:g}s"
        job.lease_expires_at = ""
        self._pending.append(str(job.job_id))
        self._persist_job(job)
        self._ensure_retry_thread()
        return True

    def _launch(self, job: Job) -> None:
        thread = threading.Thread(
            target=self._work,
            args=(job,),
            name=f"videoflow-job-{job.job_id}",
            daemon=True,
        )
        thread.start()

    def _drain_queue(self) -> None:
        launch: list[Job] = []
        with self._lock:
            running = sum(1 for job in self._jobs.values() if job.status == "running")
            self._pending.sort(
                key=lambda job_id: (
                    -self._jobs[job_id].priority,
                    self._jobs[job_id].created_at,
                )
            )
            now = datetime.now(UTC).isoformat(timespec="seconds")
            eligible: list[str] = []
            for job_id in list(self._pending):
                job = self._jobs.get(job_id)
                if job is None or job.status != "queued":
                    self._pending.remove(job_id)
                    continue
                if job.next_run and job.next_run > now:
                    continue
                eligible.append(job_id)
            for job_id in eligible:
                if running >= self._max_active:
                    break
                self._pending.remove(job_id)
                job = self._jobs[job_id]
                job.message = "Starting"
                job.next_run = ""
                launch.append(job)
                running += 1
        for job in launch:
            self._launch(job)

    def pause(self, job_id: str) -> Job:
        drain = False
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(f"Unknown job: {job_id}")
            if job.status in TERMINAL:
                return job
            if job.status == "queued":
                with contextlib.suppress(ValueError):
                    self._pending.remove(str(job.job_id))
                job.status = "paused"
                job.stage = "paused"
                job.message = "Paused"
                self._persist_job(job)
                drain = True
            else:
                job.pause_requested = True
                job.cancel_requested = True
                job.cancel_event.set()
                job.message = "Pausing"
                self._persist_job(job)
        if drain:
            self._drain_queue()
        return job

    def unpause(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(f"Unknown job: {job_id}")
            if job.status != "paused":
                return job
            job.status = "queued"
            job.stage = "queued"
            job.message = "Resuming"
            job.cancel_requested = False
            job.pause_requested = False
            job.cancel_event.clear()
            job.error = None
            self._pending.append(str(job.job_id))
            self._persist_job(job)
        self._drain_queue()
        return job

    def set_priority(self, job_id: str, priority: int) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(f"Unknown job: {job_id}")
            job.priority = int(priority)
            self._persist_job(job)
            self._pending.sort(
                key=lambda item: (
                    -self._jobs[item].priority,
                    self._jobs[item].created_at,
                )
            )
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

    def list(self, *, limit: int | None = None, offset: int = 0) -> list[Job]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)
        start = max(0, int(offset))
        if limit is None:
            return jobs[start:]
        return jobs[start : start + max(0, int(limit))]

    def cancel(self, job_id: str, *, force: bool = False) -> Job:
        drain = False
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(f"Unknown job: {job_id}")
            if job.status in TERMINAL:
                return job
            job.cancel_requested = True
            job.cancel_event.set()
            if job.status in {"queued", "waiting_approval", "waiting_input"}:
                with contextlib.suppress(ValueError):
                    self._pending.remove(str(job.job_id))
                job.status = "cancelled"
                job.stage = "cancelled"
                job.message = "Cancelled"
                job.finished_at = _now()
                drain = True
            elif force:
                job.status = "cancelled"
                job.stage = "cancelled"
                job.message = "Cancelled"
                job.finished_at = _now()
                drain = True
            else:
                job.message = "Cancellation requested"
            self._persist_job(job)
        if drain:
            self._drain_queue()
        return job

    def mark_answered(self, job_id: str, resumed_job_id: str) -> Job:
        """Mark the waiting job as superseded by the resumed run."""

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(f"Unknown job: {job_id}")
            if job.status in {"waiting_approval", "waiting_input"}:
                with contextlib.suppress(ValueError):
                    self._pending.remove(str(job.job_id))
                job.status = "answered"
                job.stage = "answered"
                job.message = f"Answered; resumed as {resumed_job_id}"
                job.finished_at = _now()
                job.lease_expires_at = ""
                self._persist_job(job)
            return job

    def remove(self, job_id: str, *, force: bool = False) -> Job:
        """Remove a job from the active list and store, stopping work if needed."""

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(f"Unknown job: {job_id}")
            job.deleted = True
            job.cancel_requested = True
            job.cancel_event.set()
            if job.status not in TERMINAL:
                job.status = "cancelled"
                job.stage = "cancelled"
                job.message = "Removed"
                job.finished_at = _now()
            with contextlib.suppress(ValueError):
                self._pending.remove(str(job.job_id))
            self._jobs.pop(str(job.job_id), None)
        try:
            from videoflow.application.database import delete_job

            delete_job(str(job.job_id))
        except Exception:
            pass
        if self._store_dir is not None:
            with contextlib.suppress(OSError):
                (self._store_dir / f"{job.job_id}.json").unlink(missing_ok=True)
        self._drain_queue()
        return job

    def cancel_all(self, *, force: bool = False) -> list[Job]:
        """Stop every queued or running job."""

        with self._lock:
            ids = [str(job.job_id) for job in self._jobs.values() if job.status not in TERMINAL]
        stopped: list[Job] = []
        for job_id in ids:
            try:
                stopped.append(self.cancel(job_id, force=force))
            except JobNotFoundError:
                continue
        return stopped

    def _work(self, job: Job) -> None:
        mode = job.options.get("mode")
        if mode == "render":
            self._work_render(job)
            return
        if mode == "step":
            self._work_step(job)
            return
        self._work_recipe(job)

    def _work_recipe(self, job: Job) -> None:
        self._executor.run(
            job,
            self._run_recipe,
            JobRunPolicy(
                record_recipe_history=True,
                write_failure=True,
                cancel_error=True,
            ),
        )

    def _work_render(self, job: Job) -> None:
        self._executor.run(
            job,
            self._run_render,
            JobRunPolicy(write_failure=True, cancel_error=True),
        )

    def _work_step(self, job: Job) -> None:
        self._executor.run(
            job,
            self._run_step,
            JobRunPolicy(write_failure=True, cancel_error=True),
        )

    def _run_step(self, job: Job, callbacks: Any) -> RunOutcome:
        from videoflow.adapters.ffmpeg import FFmpegAdapter
        from videoflow.application.projects import (
            get_project,
            load_project_state,
            save_project_state,
        )
        from videoflow.core.context import PipelineContext
        from videoflow.steps.base import StepIO
        from videoflow.steps.registry import get_step

        project_id = str(job.options.get("project_id") or job.project_id or "")
        step_type = str(job.options.get("step_type") or "")
        if not project_id or not step_type:
            raise ProjectStateError("Step job needs project_id and step_type")
        record = get_project(project_id)
        state = load_project_state(record)
        media = state.media_info
        source = Path(media.source_path) if media is not None else job.source
        output = Path(record.output)
        context = PipelineContext(
            source=source,
            output=output,
            work=output / "work",
            exports=output / "exports",
            media=media,
            state=state,
            transcript=list(state.transcript),
            metadata={"project_id": project_id, "job_id": str(job.job_id)},
        )
        step = get_step(step_type)
        params = step.params_model.model_validate(job.options.get("params") or {})
        io = StepIO(
            stage=step_type,
            adapter=FFmpegAdapter(cancel_event=job.cancel_event),
            progress=callbacks.progress,
            step_progress=callbacks.step_progress,
            should_cancel=callbacks.should_cancel,
            log=callbacks.log,
        )
        step.run(context, params, io)
        if context.state is not None:
            save_project_state(record, context.state, bump_revision=True)
        result = {
            "step_id": step_type,
            "artifacts": dict(context.artifacts),
            "warnings": list(context.warnings),
            "hashes": dict(context.hashes),
        }
        return RunOutcome(result=result)

    def _run_render(self, job: Job, callbacks: Any) -> RunOutcome:
        from videoflow.adapters.ffmpeg import FFmpegAdapter
        from videoflow.application.artifacts import qa_artifacts
        from videoflow.application.projects import get_project, load_project_state
        from videoflow.application.render_inputs import render_inputs
        from videoflow.exporters.mp4 import export_mp4

        project_id = str(job.options.get("project_id") or job.project_id or "")
        if not project_id:
            raise ProjectStateError("Render job has no project_id")
        record = get_project(project_id)
        state = load_project_state(record)
        if state.media_info is None:
            raise ProjectStateError("Project has no media")
        kind = str(job.options.get("kind") or "timeline")
        destination = (
            job.output / "render" / f"{kind}.mp4"
            if kind != "preview"
            else job.output / "preview" / "preview.mp4"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        draft = max(0.1, min(1.0, float(job.options.get("draft_scale", 1.0) or 1.0)))
        width = int(job.options.get("width") or 0)
        height = int(job.options.get("height") or 0)
        if width and not height:
            height = round(width * state.media_info.height / max(1, state.media_info.width))
        if height and not width:
            width = round(height * state.media_info.width / max(1, state.media_info.height))
        if not height:
            height = max(64, round(state.media_info.height * draft))
        if not width:
            width = max(64, round(state.media_info.width * draft))
        audio_filters, video_filters, ass_path = render_inputs(job)
        adapter = FFmpegAdapter(cancel_event=job.cancel_event)

        def progress(percent: int) -> None:
            callbacks.progress("render", max(1, min(99, percent)), f"Rendering {percent}%")

        export_mp4(
            state,
            destination,
            adapter=adapter,
            crf=int(job.options.get("crf", 20) or 20),
            preset=str(job.options.get("preset") or "veryfast"),
            audio_filters=audio_filters,
            video_filters=video_filters,
            ass_path=ass_path if ass_path.is_file() else None,
            progress=progress,
            scale_height=height,
            cache_dir=job.output / "render" / "segments",
        )
        info = adapter.probe(destination)
        loudness: dict[str, float] = {}
        with contextlib.suppress(Exception):
            loudness = adapter.measure_loudness(destination)
        qa = qa_artifacts(job.output)
        result = {
            "output_path": str(destination),
            "kind": kind,
            "duration_sec": round(
                info.duration_frames / max(0.001, info.fps_num / info.fps_den), 3
            ),
            "width": info.width,
            "height": info.height,
            "fps_num": info.fps_num,
            "fps_den": info.fps_den,
            "draft_scale": draft,
            "lufs": loudness.get("integrated_lufs"),
            "true_peak_db": loudness.get("true_peak_dbfs"),
            "qa_status": "failed" if qa["defects"] else "passed" if qa["reports"] else "not_run",
            "artifacts": [str(destination)],
        }
        return RunOutcome(result=result)

    def _run_recipe(self, job: Job, callbacks: Any) -> RunOutcome:
        from videoflow.core.recipe import Recipe
        from videoflow.engine.runner import RecipeRunner

        recipe = Recipe.model_validate(job.options.get("recipe") or {})
        transcript_sentences = [
            Sentence.model_validate(item) for item in job.options.get("transcript_sentences", [])
        ]
        from videoflow.adapters.ffmpeg import FFmpegAdapter

        runner = (
            self._recipe_runner_factory(recipe, job)
            if self._recipe_runner_factory is not None
            else RecipeRunner(
                recipe,
                adapter=FFmpegAdapter(cancel_event=job.cancel_event),
                cancel_event=job.cancel_event,
            )
        )
        base_variables = dict(job.options.get("variables") or {})
        variants = recipe.variants or []
        variant_summaries: list[dict[str, object]] = []
        result = None
        if variants:
            for index, variant in enumerate(variants, start=1):
                name = str(variant.get("name") or f"variant-{index}")
                overrides = variant.get("variables")
                variables = {
                    **base_variables,
                    **(overrides if isinstance(overrides, dict) else {}),
                }
                target = job.output / name
                variant_result = runner.run(
                    job.source,
                    target,
                    progress=callbacks.progress,
                    step_progress=callbacks.step_progress,
                    should_cancel=callbacks.should_cancel,
                    log=callbacks.log,
                    telemetry=job.telemetry,
                    transcript_sentences=transcript_sentences,
                    through=job.options.get("through"),
                    resume=bool(job.options.get("resume", True)),
                    variables=variables,
                    profile=job.options.get("profile"),
                    job_id=str(job.job_id),
                )
                variant_summaries.append(
                    {
                        "name": name,
                        "output": str(target),
                        "summary": variant_result.to_dict(),
                    }
                )
                result = variant_result
        else:
            result = runner.run(
                job.source,
                job.output,
                progress=callbacks.progress,
                step_progress=callbacks.step_progress,
                should_cancel=callbacks.should_cancel,
                log=callbacks.log,
                telemetry=job.telemetry,
                transcript_sentences=transcript_sentences,
                through=job.options.get("through"),
                resume=bool(job.options.get("resume", True)),
                variables=base_variables,
                profile=job.options.get("profile"),
                job_id=str(job.job_id),
            )
        return RunOutcome(result=result.to_dict(), variants=variant_summaries)

    def _persist_job(self, job: Job) -> None:
        if job.deleted or self._store_dir is None:
            return
        # A pruned terminal job can still be finishing its worker finalizer.
        # Do not resurrect it in the store after _prune removed it.
        if job.status in TERMINAL and self._jobs.get(str(job.job_id)) is not job:
            return
        try:
            from videoflow.application.database import upsert_job

            upsert_job(str(job.job_id), job.to_dict())
        except Exception:
            pass
        try:
            self._store_dir.mkdir(parents=True, exist_ok=True)
            path = self._store_dir / f"{job.job_id}.json"
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(job.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError as exc:
            logger.warning("could not persist job state for %s: %s", job.job_id, exc)

    def _load_jobs(self) -> None:
        if self._store_dir is None:
            return
        try:
            from videoflow.application.database import list_jobs

            for payload in list_jobs():
                job = _job_from_dict(payload)
                job.telemetry.job_id = str(job.job_id)
                self._jobs[str(job.job_id)] = job
                if job.status in {"queued", "running"}:
                    job.status = "queued"
                    job.stage = "queued"
                    job.message = "Requeued after service restart"
                    job.error = None
                    self._pending.append(str(job.job_id))
                    self._persist_job(job)
        except Exception as exc:
            logger.warning("could not load persisted jobs: %s", exc)
        if not self._store_dir.is_dir():
            self._drain_queue()
            return
        for path in sorted(self._store_dir.glob("*.json")):
            try:
                job = _job_from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if str(job.job_id) in self._jobs:
                continue
            if job.status in {"queued", "running"}:
                job.status = "queued"
                job.stage = "queued"
                job.message = "Requeued after service restart"
                job.error = None
                self._pending.append(str(job.job_id))
                self._persist_job(job)
            job.telemetry.job_id = str(job.job_id)
            self._jobs[str(job.job_id)] = job
        self._drain_queue()

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
    job.step_progress = {
        str(key): int(value)
        for key, value in (payload.get("step_progress") or {}).items()
        if isinstance(value, (int, float))
    }
    job.idempotency_key = str(payload.get("idempotency_key") or "")
    job.project_id = str(payload.get("project_id") or "")
    job.timeline_ready = bool(payload.get("timeline_ready", False))
    job.pause_requested = bool(payload.get("pause_requested", False))
    job.priority = int(payload.get("priority", 0))
    job.attempts = int(payload.get("attempts", 0) or 0)
    job.next_run = str(payload.get("next_run") or "")
    job.lease_expires_at = str(payload.get("lease_expires_at") or "")
    job.lease_owner = str(payload.get("lease_owner") or "")
    return job


def _record_recipe_history(job: Job) -> None:
    from videoflow.engine.history import append_run

    payload = job.result or {}
    recipe = job.options.get("recipe") if isinstance(job.options, dict) else None
    recipe_id = ""
    if isinstance(recipe, dict):
        recipe_id = str(recipe.get("id", ""))
    recipe_id = str(payload.get("recipe_id") or recipe_id)
    try:
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
    except OSError as exc:
        logger.warning("could not record run history for %s: %s", job.job_id, exc)
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
