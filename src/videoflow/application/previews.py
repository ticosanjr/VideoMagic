"""Background browser-preview rendering with progress and cancellation."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.domain.errors import StateNotReadyError
from videoflow.domain.state import ProjectState
from videoflow.exporters.mp4 import export_mp4


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def preview_paths(job: Any) -> tuple[Path, Path]:
    return job.output / "preview" / "timeline-preview.mp4", job.output / "preview" / "preview.mp4"


def _fallback_source(job: Any) -> Path:
    artifacts = (job.result or {}).get("artifacts") or {}
    if isinstance(artifacts, dict):
        for value in artifacts.values():
            path = Path(str(value)).expanduser()
            if path.suffix.lower() == ".mp4" and path.is_file():
                return path
    shorts = (job.result or {}).get("shorts") or []
    if isinstance(shorts, list):
        for entry in shorts:
            if isinstance(entry, dict) and entry.get("path"):
                path = Path(str(entry["path"])).expanduser()
                if path.is_file():
                    return path
    raise StateNotReadyError("The job has no MP4 artifact to preview.")


def _video_filters(job: Any) -> list[str]:
    path = job.output / "color" / "filters.json"
    if not path.is_file():
        return []
    import json

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(item) for item in payload.get("filters", []) if str(item)]


def _audio_filters(job: Any) -> list[str]:
    path = job.output / "audio" / "master-filters.json"
    if not path.is_file():
        return []
    import json

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(item) for item in payload.get("filters", []) if str(item)]


def build_preview(
    job: Any,
    *,
    progress: Callable[[int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> Path:
    full, preview = preview_paths(job)
    preview.parent.mkdir(parents=True, exist_ok=True)
    state_path = Path(
        str((job.result or {}).get("state_path") or job.output / "project_state.json")
    )

    def report(percent: int, message: str) -> None:
        if progress is not None:
            progress(percent, message)
        if should_cancel is not None and should_cancel():
            from videoflow.domain.errors import JobCancelledError

            raise JobCancelledError("Preview cancelled")

    if state_path.is_file():
        report(5, "Reading project state")
        state = ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))
        ass_path = job.output / "titles.ass"
        report(20, "Rendering timeline")
        export_mp4(
            state,
            full,
            audio_filters=_audio_filters(job),
            video_filters=_video_filters(job),
            ass_path=ass_path if ass_path.is_file() else None,
        )
    else:
        report(20, "Using the last MP4 artifact")
        FFmpegAdapter().transcode_preview(_fallback_source(job), full)
    report(80, "Building 540p proxy")
    FFmpegAdapter().transcode_preview(full, preview)
    report(100, "Preview ready")
    return preview


@dataclass
class PreviewState:
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


class PreviewManager:
    def __init__(self) -> None:
        self._items: dict[str, PreviewState] = {}
        self._lock = threading.Lock()

    def start(self, job: Any) -> PreviewState:
        with self._lock:
            active = self._items.get(str(job.job_id))
            if active is not None and active.status in {"queued", "rendering"}:
                return active
            item = PreviewState(job_id=str(job.job_id))
            self._items[str(job.job_id)] = item
        thread = threading.Thread(
            target=self._work,
            args=(job, item),
            name=f"videoflow-preview-{job.job_id}",
            daemon=True,
        )
        thread.start()
        return item

    def _work(self, job: Any, item: PreviewState) -> None:
        with self._lock:
            item.status = "rendering"
            item.message = "Starting"

        def progress(percent: int, message: str) -> None:
            with self._lock:
                item.percent = percent
                item.message = message

        def cancelled() -> bool:
            with self._lock:
                return item.cancel_requested

        try:
            build_preview(job, progress=progress, should_cancel=cancelled)
        except Exception as exc:
            with self._lock:
                if item.cancel_requested:
                    item.status = "cancelled"
                    item.message = "Cancelled"
                else:
                    item.status = "failed"
                    item.error = str(exc)
                    item.message = "Preview failed"
                item.finished_at = _now()
            return
        with self._lock:
            item.status = "ready"
            item.percent = 100
            item.message = "Preview ready"
            item.finished_at = _now()

    def cancel(self, job_id: str) -> PreviewState | None:
        with self._lock:
            item = self._items.get(job_id)
            if item is None:
                return None
            if item.status in {"queued", "rendering"}:
                item.cancel_requested = True
            return item

    def get(self, job_id: str) -> PreviewState | None:
        with self._lock:
            return self._items.get(job_id)


previews = PreviewManager()
