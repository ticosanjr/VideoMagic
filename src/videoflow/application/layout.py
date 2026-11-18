"""Deterministic overlay auto-packing and layout audit."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.application.overlay_geometry import (
    auto_pack,
    caption_box,
    collisions,
    layout_payload,
    write_layout,
)
from videoflow.application.projects import get_project, load_project_state, save_project_state
from videoflow.domain.errors import ExportError


def pack_project_layout(
    project_id: str,
    *,
    platform: str = "youtube_16_9",
    apply: bool = True,
) -> dict[str, Any]:
    record = get_project(project_id)
    state = load_project_state(record)
    media = state.media_info
    if media is None:
        raise ExportError("Project has no media")
    style = state.modules_config.shorts.caption_style
    caption = caption_box(style, media.width, media.height)
    changes = auto_pack(state, media.width, media.height, caption=caption)
    if apply and changes:
        updates = {}
        by_id = {item["overlay_id"]: item for item in changes}
        overlays = []
        for overlay in state.overlays:
            change = by_id.get(overlay.overlay_id)
            if change is None:
                overlays.append(overlay)
                continue
            overlays.append(
                overlay.model_copy(
                    update={"margin_y": max(0, int(change["margin_y"]))}
                )
            )
        updates["overlays"] = overlays
        state = state.model_copy(update=updates)
        state = save_project_state(
            record,
            state,
            bump_revision=True,
            snapshot=True,
            snapshot_reason="layout.autofix",
            snapshot_step="layout.autofix",
        )
    layout_path = write_layout(
        state, Path(record.output), media.width, media.height, caption=caption
    )
    return {
        "ok": True,
        "project_id": project_id,
        "platform": platform,
        "changes": changes,
        "collisions": collisions(state, media.width, media.height, caption=caption),
        "layout_path": str(layout_path),
        "layout": layout_payload(state, media.width, media.height, caption=caption),
        "revision": state.revision,
    }


__all__ = ["pack_project_layout"]
