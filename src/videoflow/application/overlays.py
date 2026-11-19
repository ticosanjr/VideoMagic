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
    anchor: str = "top_center",
    margin_x: int = 0,
    margin_y: int = 0,
    scale: float = 0.25,
    z: int = 20,
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
        anchor=anchor,  # type: ignore[arg-type]
        margin_x=max(0, int(margin_x)),
        margin_y=max(0, int(margin_y)),
        width_ratio=max(0.01, min(1.0, float(scale))),
        z=max(0, min(1000, int(z))),
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


def update_overlay(
    project_id: str,
    overlay_id: str,
    *,
    asset_path: str = "",
    at_timeline_sec: float | None = None,
    duration_sec: float | None = None,
    anchor: str | None = None,
    margin_x: int | None = None,
    margin_y: int | None = None,
    scale: float | None = None,
    z: int | None = None,
    opacity: float | None = None,
    transition_in: str | None = None,
    transition_out: str | None = None,
) -> dict[str, Any]:
    record = get_project(project_id)
    state = load_project_state(record)
    current = next(
        (item for item in state.overlays if item.overlay_id == overlay_id),
        None,
    )
    if current is None:
        raise ExportError(f"Unknown overlay: {overlay_id}")
    media = state.media_info
    if media is None:
        raise ExportError("Project has no media")
    fps = media.fps_num / media.fps_den
    updates: dict[str, Any] = {}
    if asset_path:
        asset = Path(asset_path).expanduser()
        if not asset.is_file():
            raise ExportError(f"Overlay asset does not exist: {asset}")
        updates["path"] = str(asset)
        updates["kind"] = "video" if asset.suffix.casefold() in VIDEO_SUFFIXES else "image"
    if at_timeline_sec is not None:
        updates["start_frame"] = max(0, round(float(at_timeline_sec) * fps))
    if duration_sec is not None:
        updates["duration_frames"] = max(1, round(max(0.1, float(duration_sec)) * fps))
    if anchor is not None:
        updates["anchor"] = anchor
    if margin_x is not None:
        updates["margin_x"] = max(0, int(margin_x))
    if margin_y is not None:
        updates["margin_y"] = max(0, int(margin_y))
    if scale is not None:
        updates["width_ratio"] = max(0.01, min(1.0, float(scale)))
    if z is not None:
        updates["z"] = max(0, min(1000, int(z)))
    if opacity is not None:
        updates["opacity"] = max(0.0, min(1.0, float(opacity)))
    if transition_in is not None:
        updates["transition_in"] = transition_in
    if transition_out is not None:
        updates["transition_out"] = transition_out
    updated_clip = OverlayClip.model_validate(
        {**current.model_dump(mode="python"), **updates}
    )
    overlays = [
        updated_clip if item.overlay_id == overlay_id else item
        for item in state.overlays
    ]
    saved = save_project_state(
        record,
        state.model_copy(update={"overlays": overlays}),
        bump_revision=True,
        snapshot=True,
        snapshot_reason="overlay.update",
        snapshot_step="overlay.update",
    )
    return {
        "ok": True,
        "project_id": project_id,
        "revision": saved.revision,
        "overlay": updated_clip.model_dump(mode="json"),
    }


def remove_overlay(project_id: str, overlay_id: str) -> dict[str, Any]:
    record = get_project(project_id)
    state = load_project_state(record)
    kept = [item for item in state.overlays if item.overlay_id != overlay_id]
    if len(kept) == len(state.overlays):
        raise ExportError(f"Unknown overlay: {overlay_id}")
    saved = save_project_state(
        record,
        state.model_copy(update={"overlays": kept}),
        bump_revision=True,
        snapshot=True,
        snapshot_reason="overlay.remove",
        snapshot_step="overlay.remove",
    )
    return {
        "ok": True,
        "project_id": project_id,
        "revision": saved.revision,
        "removed": overlay_id,
        "count": len(kept),
    }


def list_overlays(project_id: str) -> dict[str, Any]:
    record = get_project(project_id)
    state = load_project_state(record)
    return {
        "ok": True,
        "project_id": project_id,
        "overlays": [item.model_dump(mode="json") for item in state.overlays],
        "count": len(state.overlays),
    }


__all__ = [
    "add_overlay",
    "list_overlays",
    "remove_overlay",
    "update_overlay",
]
