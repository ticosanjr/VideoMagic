"""Background browser-preview rendering with progress and cancellation."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.clock import now_iso as _now
from videoflow.application.files import stat_signature
from videoflow.application.render_inputs import audio_filters, video_filters
from videoflow.domain.errors import StateNotReadyError, VideoFlowError
from videoflow.domain.state import ProjectState
from videoflow.exporters.mp4 import export_mp4

PREVIEW_CACHE_VERSION = 1


def preview_paths(job: Any) -> tuple[Path, Path]:
    return job.output / "preview" / "timeline-preview.mp4", job.output / "preview" / "preview.mp4"


def preview_manifest_path(job: Any) -> Path:
    return job.output / "preview" / "manifest.json"


def proxy_height() -> int:
    try:
        from videoflow.application.settings import load_settings

        return int(load_settings().quality.proxy_height)
    except Exception:
        return 540


def preview_key(job: Any) -> str:
    state_path = Path(
        str((job.result or {}).get("state_path") or job.output / "project_state.json")
    )
    if state_path.is_file():
        state_bytes = state_path.read_bytes()
        fallback = ""
    else:
        artifact = _fallback_source(job)
        stat = artifact.stat()
        state_bytes = b""
        fallback = f"{artifact.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    ass_path = job.output / "titles.ass"
    payload = {
        "version": PREVIEW_CACHE_VERSION,
        "audio_filters": audio_filters(job),
        "video_filters": video_filters(job),
        "ass_mtime": str(ass_path.stat().st_mtime_ns if ass_path.is_file() else 0),
        "height": proxy_height(),
        "fallback": fallback,
    }
    return hashlib.sha256(
        state_bytes + json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


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


def build_preview(
    job: Any,
    *,
    progress: Callable[[int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    cancel_event: Any | None = None,
    state: ProjectState | None = None,
) -> Path:
    _full, preview = preview_paths(job)
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

    height = proxy_height()
    temporary = preview.with_name(f".{preview.stem}.{threading.get_ident()}.part.mp4")
    try:
        if state_path.is_file():
            report(5, "Reading project state")
            loaded = state or ProjectState.model_validate_json(
                state_path.read_text(encoding="utf-8")
            )
            ass_path = job.output / "titles.ass"
            report(20, "Rendering preview")
            adapter = FFmpegAdapter(cancel_event=cancel_event)
            export_mp4(
                loaded,
                temporary,
                adapter=adapter,
                audio_filters=audio_filters(job),
                video_filters=video_filters(job),
                ass_path=ass_path if ass_path.is_file() else None,
                scale_height=height,
                cache_dir=job.output / "render" / "segments",
            )
        else:
            report(20, "Using the last MP4 artifact")
            FFmpegAdapter(cancel_event=cancel_event).transcode_preview(
                _fallback_source(job), temporary, width=height
            )
        report(95, "Finalizing preview")
        temporary.replace(preview)
        report(100, "Preview ready")
        return preview
    finally:
        temporary.unlink(missing_ok=True)


def preview_inputs(job: Any) -> dict[str, object]:
    state_path = Path(
        str((job.result or {}).get("state_path") or job.output / "project_state.json")
    )
    ass_path = job.output / "titles.ass"
    payload: dict[str, object] = {
        "state": stat_signature(state_path),
        "audio": stat_signature(job.output / "audio" / "master-filters.json"),
        "video": stat_signature(job.output / "color" / "filters.json"),
        "ass": stat_signature(ass_path),
        "height": proxy_height(),
    }
    if not state_path.is_file():
        try:
            artifact = _fallback_source(job)
            payload["fallback"] = stat_signature(artifact)
        except StateNotReadyError:
            payload["fallback"] = None
    return payload


def write_preview_manifest(
    job: Any, *, key: str | None = None, revision: int | None = None
) -> int:
    """Record a finished preview so status and downloads can trust it."""

    state_path = Path(
        str((job.result or {}).get("state_path") or job.output / "project_state.json")
    )
    if revision is None:
        revision = (
            ProjectState.model_validate_json(
                state_path.read_text(encoding="utf-8")
            ).revision
            if state_path.is_file()
            else 0
        )
    if key is None:
        key = preview_key(job)
    manifest = preview_manifest_path(job)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest.with_name(f".{manifest.name}.{threading.get_ident()}.tmp")
    temporary.write_text(
        json.dumps(
            {
                "key": key,
                "revision": revision,
                "height": proxy_height(),
                "inputs": preview_inputs(job),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(manifest)
    return revision


@dataclass
class PreviewState:
    job_id: str
    status: str = "queued"
    percent: int = 0
    message: str = "Queued"
    error: str = ""
    error_details: dict[str, object] = field(default_factory=dict)
    started_at: str = field(default_factory=_now)
    finished_at: str = ""
    cancel_requested: bool = False
    revision: int = 0
    key: str = ""
    cancel_event: Any = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "percent": self.percent,
            "message": self.message,
            "error": self.error,
            "error_details": dict(self.error_details),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "cancel_requested": self.cancel_requested,
            "revision": self.revision,
        }


class PreviewManager:
    def __init__(self) -> None:
        self._items: dict[str, PreviewState] = {}
        self._lock = threading.Lock()

    def is_ready(self, job: Any) -> bool:
        preview = preview_paths(job)[1]
        if not preview.is_file() or preview.stat().st_size == 0:
            return False
        try:
            manifest = json.loads(
                preview_manifest_path(job).read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return False
        if not isinstance(manifest, dict):
            return False
        inputs = manifest.get("inputs")
        if isinstance(inputs, dict):
            try:
                return inputs == preview_inputs(job)
            except (OSError, VideoFlowError):
                return False
        try:
            return manifest.get("key") == preview_key(job)
        except (OSError, VideoFlowError):
            return False

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
            state_path = Path(
                str(
                    (job.result or {}).get("state_path")
                    or job.output / "project_state.json"
                )
            )
            state = (
                ProjectState.model_validate_json(
                    state_path.read_text(encoding="utf-8")
                )
                if state_path.is_file()
                else None
            )
            try:
                key = preview_key(job)
            except (OSError, VideoFlowError):
                key = ""
            revision = state.revision if state is not None else 0
            with self._lock:
                item.key = key
                item.revision = revision
            if self.is_ready(job):
                with self._lock:
                    item.status = "ready"
                    item.percent = 100
                    item.message = "Preview ready (cached)"
                    item.finished_at = _now()
                return
            build_preview(
                job,
                progress=progress,
                should_cancel=cancelled,
                cancel_event=item.cancel_event,
                state=state,
            )
            if cancelled():
                preview_paths(job)[1].unlink(missing_ok=True)
                raise RuntimeError("Preview cancelled")
            if key:
                write_preview_manifest(job, key=key, revision=revision)
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
                        else {"ok": False, "code": "preview_failed", "message": str(exc)}
                    )
                    item.message = "Preview failed"
                item.finished_at = _now()
            if item.cancel_requested:
                preview_paths(job)[1].unlink(missing_ok=True)
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
                item.cancel_event.set()
            return item

    def get(self, job_id: str) -> PreviewState | None:
        with self._lock:
            return self._items.get(job_id)


previews = PreviewManager()
