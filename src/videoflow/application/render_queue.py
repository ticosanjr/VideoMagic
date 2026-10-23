"""Background MP4 render queue for the edited timeline."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from videoflow.domain.errors import JobCancelledError, StateNotReadyError
from videoflow.domain.state import ProjectState
from videoflow.exporters.mp4 import export_mp4


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _filters(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(item) for item in payload.get("filters", []) if str(item)]


@dataclass
class RenderState:
    job_id: str
    status: str = "queued"
    percent: int = 0
    message: str = "Queued"
    error: str = ""
    started_at: str = field(default_factory=_now)
    finished_at: str = ""
    cancel_requested: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "percent": self.percent,
            "message": self.message,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "cancel_requested": self.cancel_requested,
        }


class RenderQueue:
    def __init__(self) -> None:
        self._items: dict[str, RenderState] = {}
        self._lock = threading.Lock()
        self._slot = threading.Semaphore(1)

    def output_path(self, job: Any) -> Path:
        return job.output / "render" / "timeline.mp4"

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

        with self._slot:
            with self._lock:
                item.status = "rendering"
                item.message = "Starting render"
            try:
                state_path = Path(
                    str(
                        (job.result or {}).get("state_path")
                        or job.output / "project_state.json"
                    )
                )
                if not state_path.is_file():
                    raise StateNotReadyError("The job has no project_state.json to render.")
                state = ProjectState.model_validate_json(
                    state_path.read_text(encoding="utf-8")
                )
                if cancelled():
                    raise JobCancelledError("Render cancelled")
                progress(15, "Rendering timeline")
                destination = self.output_path(job)
                ass_path = job.output / "titles.ass"
                export_mp4(
                    state,
                    destination,
                    audio_filters=_filters(job.output / "audio" / "master-filters.json"),
                    video_filters=_filters(job.output / "color" / "filters.json"),
                    ass_path=ass_path if ass_path.is_file() else None,
                )
                if cancelled():
                    destination.unlink(missing_ok=True)
                    raise JobCancelledError("Render cancelled")
                progress(100, "Render ready")
            except Exception as exc:
                with self._lock:
                    if item.cancel_requested:
                        item.status = "cancelled"
                        item.message = "Cancelled"
                    else:
                        item.status = "failed"
                        item.error = str(exc)
                        item.message = "Render failed"
                    item.finished_at = _now()
                return
        with self._lock:
            item.status = "ready"
            item.percent = 100
            item.message = "Render ready"
            item.finished_at = _now()

    def cancel(self, job_id: str) -> RenderState | None:
        with self._lock:
            item = self._items.get(job_id)
            if item is None:
                return None
            if item.status in {"queued", "rendering"}:
                item.cancel_requested = True
            return item

    def get(self, job_id: str) -> RenderState | None:
        with self._lock:
            return self._items.get(job_id)


renders = RenderQueue()
