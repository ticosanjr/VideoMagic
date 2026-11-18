"""Declarative overlay insertion by source or timeline time."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.application.projects import get_project, load_project_state, save_project_state
from videoflow.application.time_map import source_to_timeline_sec
from videoflow.domain.errors import ExportError
from videoflow.domain.state import OverlayClip

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def add_overlay(
    project_id: str,
    asset_path: str,
    *,
    at_source_sec: float | None = None,
    at_timeline_sec: float | None = None,
    duration_sec: float = 3.0,
    x: float = 0.5,
    y: float = 0.5,
    scale: float = 0.25,
    opacity: float = 1.0,
    transition_in: str = "fade",
    transition_out: str = "fade",
    transition_frames: int = 6,
) -> dict[str, Any]:
    record = get_project(project_id)
    state = load_project_state(record)
    media = state.media_info
    if media is None:
        raise ExportError("Project has no media")
    asset = Path(asset_path).expanduser()
    if not asset.is_file():
        raise ExportError(f"Overlay asset does not exist: {asset}")
    if at_source_sec is not None:
        timeline_sec = source_to_timeline_sec(state, float(at_source_sec))
    else:
        timeline_sec = max(0.0, float(at_timeline_sec or 0.0))
    fps = media.fps_num / media.fps_den
    start_frame = max(0, round(timeline_sec * fps))
    duration_frames = max(1, round(max(0.1, float(duration_sec)) * fps))
    overlay = OverlayClip(
        overlay_id=f"overlay-{len(state.overlays) + 1}",
        path=str(asset),
        start_frame=start_frame,
        duration_frames=duration_frames,
        position_x=max(0.0, min(1.0, float(x))),
        position_y=max(0.0, min(1.0, float(y))),
        width_ratio=max(0.01, min(1.0, float(scale))),
        opacity=max(0.0, min(1.0, float(opacity))),
        kind="video" if asset.suffix.casefold() in VIDEO_SUFFIXES else "image",
        transition_in=transition_in,
        transition_out=transition_out,
        transition_frames=max(0, min(120, int(transition_frames))),
    )
    updated = state.model_copy(update={"overlays": [*state.overlays, overlay]})
    saved = save_project_state(
        record,
        updated,
        bump_revision=True,
        snapshot=True,
        snapshot_reason="overlay.insert",
        snapshot_step="overlay.insert",
    )
    return {
        "ok": True,
        "project_id": project_id,
        "revision": saved.revision,
        "overlay": overlay.model_dump(mode="json"),
        "timeline_sec": round(timeline_sec, 3),
    }


__all__ = ["add_overlay"]
