"""Background MP4 render queue for the edited timeline."""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.clock import now_iso as _now
from videoflow.application.files import read_json_dict, stat_signature, write_json_atomic
from videoflow.application.render_gate import render_gate
from videoflow.application.render_inputs import render_inputs as _render_inputs
from videoflow.application.worker_state import WorkerState
from videoflow.domain.errors import (
    JobCancelledError,
    StateNotReadyError,
    VideoFlowError,
)
from videoflow.domain.state import ProjectState
from videoflow.exporters.mp4 import export_mp4

RENDER_CACHE_VERSION = "3.5"


def _state_path(job: Any) -> Path:
    return Path(str((job.result or {}).get("state_path") or job.output / "project_state.json"))


def render_key(job: Any) -> str:
    """Hash everything that changes the rendered frames or audio."""

    state_path = _state_path(job)
    if not state_path.is_file():
        raise StateNotReadyError("The job has no project_state.json to render.")
    audio_filters, video_filters, ass_path = _render_inputs(job)
    payload = {
        "version": RENDER_CACHE_VERSION,
        "audio_filters": audio_filters,
        "video_filters": video_filters,
        "ass_mtime": str(ass_path.stat().st_mtime_ns if ass_path.is_file() else 0),
    }
    return hashlib.sha256(
        state_path.read_bytes() + json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _manifest_path(output: Path) -> Path:
    return output.parent / "manifest.json"


def _inputs_signature(job: Any) -> dict[str, object]:
    state_path = _state_path(job)
    audio_filters, video_filters, ass_path = _render_inputs(job)
    return {
        "state": stat_signature(state_path),
        "audio": stat_signature(job.output / "audio" / "master-filters.json"),
        "video": stat_signature(job.output / "color" / "filters.json"),
        "ass": stat_signature(ass_path),
        "audio_filters": audio_filters,
        "video_filters": video_filters,
    }


def _write_manifest(path: Path, key: str, source: Path, inputs: dict[str, object]) -> None:
    write_json_atomic(path, {"key": key, "source": str(source), "inputs": inputs})


@dataclass
class RenderState(WorkerState):
    """Render worker state; the lifecycle fields live in ``WorkerState``."""


class RenderQueue:
    def __init__(self) -> None:
        self._items: dict[str, RenderState] = {}
        self._lock = threading.Lock()
        self._slot = threading.Semaphore(1)

    def output_path(self, job: Any) -> Path:
        return job.output / "render" / "timeline.mp4"

    def is_ready(self, job: Any) -> bool:
        output = self.output_path(job)
        if not output.is_file() or output.stat().st_size == 0:
            return False
        manifest = read_json_dict(_manifest_path(output))
        inputs = manifest.get("inputs")
        if isinstance(inputs, dict):
            try:
                return inputs == _inputs_signature(job)
            except (OSError, VideoFlowError):
                return False
        try:
            return manifest.get("key") == render_key(job)
        except (OSError, VideoFlowError):
            return False

    def start(self, job: Any) -> RenderState:
        with self._lock:
            active = self._items.get(str(job.job_id))
            if active is not None and active.status in {"queued", "rendering"}:
                return active
            item = RenderState(job_id=str(job.job_id))
            self._items[str(job.job_id)] = item
        thread = threading.Thread(
            target=self._work,
            args=(job, item),
            name=f"videoflow-render-{job.job_id}",
            daemon=True,
        )
        thread.start()
        return item

    def _work(self, job: Any, item: RenderState) -> None:
        with self._lock:
            item.status = "queued"
            item.message = "Waiting for the render slot"

        def progress(percent: int, message: str) -> None:
            with self._lock:
                item.percent = percent
                item.message = message

        def cancelled() -> bool:
            with self._lock:
                return item.cancel_requested

        with self._slot, render_gate.hold("timeline", str(job.job_id)):
            with self._lock:
                item.status = "rendering"
                item.message = "Starting render"
            try:
                state_path = _state_path(job)
                if not state_path.is_file():
                    raise StateNotReadyError("The job has no project_state.json to render.")
                state = ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))
                if cancelled():
                    raise JobCancelledError("Render cancelled")
                progress(15, "Rendering timeline")
                destination = self.output_path(job)
                audio_filters, video_filters, ass_path = _render_inputs(job)
                key = render_key(job)
                if self.is_ready(job):
                    with self._lock:
                        item.status = "ready"
                        item.percent = 100
                        item.message = "Render ready (cached)"
                        item.finished_at = _now()
                    return
                adapter = FFmpegAdapter(cancel_event=item.cancel_event)

                def frame_progress(percent: int) -> None:
                    progress(15 + int(max(0, min(100, percent)) * 0.8), f"Rendering {percent}%")

                export_mp4(
                    state,
                    destination,
                    adapter=adapter,
                    audio_filters=audio_filters,
                    video_filters=video_filters,
                    ass_path=ass_path if ass_path.is_file() else None,
                    progress=frame_progress,
                    cache_dir=job.output / "render" / "segments",
                )
                if cancelled():
                    destination.unlink(missing_ok=True)
                    raise JobCancelledError("Render cancelled")
                _write_manifest(
                    _manifest_path(destination),
                    key,
                    state_path,
                    _inputs_signature(job),
                )
                progress(100, "Render ready")
                with self._lock:
                    item.status = "ready"
                    item.percent = 100
                    item.message = "Render ready"
                    item.finished_at = _now()
                return
            except Exception as exc:
                with self._lock:
                    if item.cancel_requested:
                        item.status = "cancelled"
                        item.message = "Cancelled"
                    else:
                        item.status = "failed"
                        item.error = str(exc)
                        item.error_details = (
                            exc.to_dict()
                            if isinstance(exc, VideoFlowError)
                            else {"ok": False, "code": "render_failed", "message": str(exc)}
                        )
                        item.message = "Render failed"
                    item.finished_at = _now()
                if item.cancel_requested:
                    self.output_path(job).unlink(missing_ok=True)
                return

    def cancel(self, job_id: str) -> RenderState | None:
        with self._lock:
            item = self._items.get(job_id)
            if item is None:
                return None
            if item.status in {"queued", "rendering"}:
                item.cancel_requested = True
                item.cancel_event.set()
            return item

    def get(self, job_id: str) -> RenderState | None:
        with self._lock:
            return self._items.get(job_id)


renders = RenderQueue()
