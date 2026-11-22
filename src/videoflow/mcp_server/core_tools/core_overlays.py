"""VideoFlow core MCP tools: overlays."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.application.projects import get_project, load_project_state
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.context import error


def register(register: Any, ctx: Any, legacy: dict[str, Any]) -> None:
    @register
    def vf_overlay(
        project_id: str,
        asset_path: str = "",
        at_source_sec: float | None = None,
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
        action: str = "add",
        overlay_id: str = "",
    ) -> dict[str, Any]:
        """Insert, update, remove, or list image/video overlays."""

        from videoflow.application.overlays import (
            add_overlay,
            list_overlays,
            remove_overlay,
            update_overlay,
        )

        try:
            if action == "list":
                return list_overlays(project_id)
            if action == "remove":
                return remove_overlay(project_id, overlay_id)
            if action == "update":
                return update_overlay(
                    project_id,
                    overlay_id,
                    asset_path=asset_path,
                    at_timeline_sec=at_timeline_sec,
                    duration_sec=duration_sec,
                    anchor=anchor,
                    margin_x=margin_x,
                    margin_y=margin_y,
                    scale=scale,
                    z=z,
                    opacity=opacity,
                    transition_in=transition_in,
                    transition_out=transition_out,
                )
            if action != "add":
                return error(
                    "unknown_action",
                    "vf_overlay supports add, update, remove, or list",
                )
            return add_overlay(
                project_id,
                asset_path,
                at_source_sec=at_source_sec,
                at_timeline_sec=at_timeline_sec,
                duration_sec=duration_sec if duration_sec is not None else 3.0,
                anchor=anchor or "top_center",
                margin_x=margin_x or 0,
                margin_y=margin_y or 0,
                scale=scale if scale is not None else 0.25,
                z=z if z is not None else 20,
                opacity=opacity if opacity is not None else 1.0,
                transition_in=transition_in or "fade",
                transition_out=transition_out or "fade",
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except ValueError as exc:
            return error("overlay_failed", str(exc))

    @register
    def vf_overlay_preview(
        project_id: str,
        time_sec: float = 0.0,
        platform: str = "youtube_16_9",
        action: str = "overlay",
        aspect: str = "9:16",
        fx: float = 0.5,
        fy: float = 0.5,
        face_center_lock: bool = False,
    ) -> dict[str, Any]:
        """Render overlay boxes or a crop rectangle preview frame."""

        if action == "crop":
            from videoflow.application.crop_preview import render_crop_preview

            try:
                record = get_project(project_id)
                state = load_project_state(record)
                source = Path(
                    state.media_info.source_path
                    if state.media_info is not None
                    else record.primary_source
                )
                if not source.is_file():
                    return error("source_not_found", f"Project source is missing: {source}")
                result = render_crop_preview(
                    source,
                    Path(record.output),
                    time_sec=time_sec,
                    aspect=aspect,
                    fx=fx,
                    fy=fy,
                    face_center_lock=face_center_lock,
                )
            except VideoFlowError as exc:
                return exc.to_dict()
            except ValueError as exc:
                return error("invalid_crop", str(exc))
            return {"ok": True, "project_id": project_id, "preview": result}
        from videoflow.application.overlay_preview import render_overlay_preview

        try:
            record = get_project(project_id)
            state = load_project_state(record)
            result = render_overlay_preview(
                state, Path(record.output), time_sec=time_sec, platform=platform
            )
        except (VideoFlowError, OSError) as exc:
            return error("overlay_preview_failed", str(exc))
        return {"ok": True, "project_id": project_id, "preview": result}

    @register
    def vf_layout(
        project_id: str,
        platform: str = "youtube_16_9",
        apply: bool = True,
    ) -> dict[str, Any]:
        """Auto-pack overlays away from the caption band and write layout.json."""

        from videoflow.application.layout import pack_project_layout

        try:
            result = pack_project_layout(project_id, platform=platform, apply=apply)
        except (VideoFlowError, OSError) as exc:
            return error("layout_failed", str(exc))
        return result

    @register
    def vf_caption_preview(project_id: str, time_sec: float = 0.0) -> dict[str, Any]:
        """Render before/during/after frames for the active caption."""

        from videoflow.application.caption_preview import render_caption_preview

        try:
            record = get_project(project_id)
            state = load_project_state(record)
            result = render_caption_preview(
                state, Path(record.output), time_sec=time_sec
            )
        except (VideoFlowError, OSError) as exc:
            return error("caption_preview_failed", str(exc))
        return {"ok": True, "project_id": project_id, "preview": result}

    @register
    def vf_qa_autofix(
        project_id: str,
        apply: bool = True,
        rerender: bool = False,
        video_path: str = "",
    ) -> dict[str, Any]:
        """Resolve overlay/caption collisions, optionally re-render the master."""

        from videoflow.application.layout import pack_project_layout

        try:
            result = pack_project_layout(
                project_id,
                apply=apply,
                rerender=rerender,
                video_path=video_path,
            )
        except (VideoFlowError, OSError) as exc:
            return error("qa_autofix_failed", str(exc))
        return result
