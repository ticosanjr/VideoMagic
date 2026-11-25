"""VideoFlow core MCP tools: media and assets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.application.projects import get_project, load_project_state
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.context import error, unknown_action


def register(register: Any, ctx: Any, legacy: dict[str, Any]) -> None:
    @register
    def vf_media(
        action: str = "list",
        project_id: str = "",
        query: str = "",
        count: int = 5,
        provider: str = "auto",
        image_path: str = "",
        duration_sec: float = 4.0,
        motion: str = "zoom_in",
        aspect_ratio: str = "",
        prompt: str = "",
        type: str = "music",
        asset_ids: list[str] | None = None,
        license: str = "",
        attribution: str = "",
        reason: str = "",
        name: str = "",
        url: str = "",
        start_time: float = 0.0,
        end_time: float = 0.0,
        audio_only: bool = False,
        max_height: int = 1080,
        orientation: str = "landscape",
        min_duration: int = 4,
        max_results: int = 5,
        keyless: bool = True,
        max_duration: float = 5.0,
        license_filter: str = "cc0",
    ) -> dict[str, Any]:
        """Fetch, animate, audit, or approve stock/media and licenses.

        [ACTIONS] search, fetch_stock_images, fetch_stock_broll, rip_video_segment,
        fetch_sfx, image_to_broll_motion, generate_music_or_sfx, list,
        license_audit, approve_license.
        """

        try:
            from videoflow.domains.media import fetch_tools

            if action == "search":
                if not project_id:
                    return error("project_required", "project_id is required")
                if type.strip().lower() in {"video", "broll"}:
                    return fetch_tools.fetch_stock_broll(
                        project_id,
                        query,
                        orientation=orientation,
                        min_duration=min_duration,
                        max_results=max_results,
                        provider=provider,
                    )
                return fetch_tools.fetch_stock_images(
                    project_id,
                    query,
                    count=count,
                    keyless=keyless,
                    provider=provider,
                )
            if action == "fetch_stock_images":
                if not project_id:
                    return error("project_required", "project_id is required")
                return fetch_tools.fetch_stock_images(
                    project_id,
                    query,
                    count=count,
                    keyless=keyless,
                    provider=provider,
                )
            if action == "fetch_stock_broll":
                if not project_id:
                    return error("project_required", "project_id is required")
                return fetch_tools.fetch_stock_broll(
                    project_id,
                    query,
                    orientation=orientation,
                    min_duration=min_duration,
                    max_results=max_results,
                    provider=provider,
                )
            if action == "rip_video_segment":
                if not project_id:
                    return error("project_required", "project_id is required")
                return fetch_tools.rip_video_segment(
                    project_id,
                    url,
                    start_time,
                    end_time,
                    audio_only=audio_only,
                    max_height=max_height,
                )
            if action == "fetch_sfx":
                if not project_id:
                    return error("project_required", "project_id is required")
                return fetch_tools.fetch_sfx(
                    project_id,
                    query,
                    max_duration=max_duration,
                    license_filter=license_filter,
                    provider=provider,
                )
            if action == "image_to_broll_motion":
                from videoflow.domains.vision.tools import image_to_broll_motion

                if not project_id:
                    return error("project_required", "project_id is required")
                return image_to_broll_motion(
                    project_id,
                    image_path,
                    duration_sec=duration_sec,
                    motion=motion,
                    aspect_ratio=aspect_ratio,
                )
            if action == "generate_music_or_sfx":
                from videoflow.domains.audio.studio import generate_music_or_sfx

                if not project_id:
                    return error("project_required", "project_id is required")
                return generate_music_or_sfx(
                    project_id, prompt, duration_sec=duration_sec, type=type
                )
            if action in {"list", "license_audit", "approve_license"}:
                if not project_id:
                    return error("project_required", "project_id is required")
                from videoflow.domains.media.assets_service import (
                    asset_records,
                    review_assets,
                )
                from videoflow.domains.media.ledger import license_blockers

                record = get_project(project_id)
                state = load_project_state(record)
                if action == "approve_license":
                    return review_assets(
                        Path(record.output),
                        action="approve",
                        project_id=record.project_id,
                        asset_ids=asset_ids,
                        license=license,
                        attribution=attribution,
                        reason=reason,
                    )
                records = asset_records(
                    Path(record.output), project_id=record.project_id, state=state
                )
                blockers = license_blockers(
                    Path(record.output), state=state, scope="timeline"
                )
                return {
                    "ok": True,
                    "assets": records,
                    "referenced": [item for item in records if item.get("referenced")],
                    "blockers": blockers,
                    "blocking_count": len(blockers),
                }
            return unknown_action(
                "vf_media",
                action,
                (
                    "search",
                    "fetch_stock_images",
                    "fetch_stock_broll",
                    "rip_video_segment",
                    "fetch_sfx",
                    "image_to_broll_motion",
                    "generate_music_or_sfx",
                    "list",
                    "license_audit",
                    "approve_license",
                ),
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except Exception as exc:  # noqa: BLE001 - keep MCP errors structured
            return error("media_failed", str(exc))

    @register
    def vf_assets(
        action: str = "list",
        project_id: str = "",
        asset_ids: list[str] | None = None,
        license: str = "",
        attribution: str = "",
        reason: str = "",
        font_path: str = "",
        name: str = "",
    ) -> dict[str, Any]:
        """List assets, licenses, or fonts; approve, quarantine, or register fonts."""

        from videoflow.domains.media.assets_service import (
            asset_records,
            review_assets,
        )

        if action in {"fonts", "register_font", "install_font"}:
            from videoflow.application.fonts import (
                font_aliases,
                list_fonts,
                list_system_fonts,
                register_font,
            )

            if action == "fonts":
                return {
                    "ok": True,
                    "fonts": list_fonts(),
                    "system": list_system_fonts(),
                    "aliases": font_aliases(),
                }
            if not font_path:
                return error("font_required", "font_path is required")
            try:
                record = register_font(Path(font_path), name=name)
            except VideoFlowError as exc:
                return exc.to_dict()
            return {"ok": True, "action": action, "font": record}
        if action not in {"list", "approve", "quarantine"}:
            return unknown_action(
                "vf_assets",
                action,
                ("list", "approve", "quarantine", "fonts", "register_font"),
            )
        if not project_id:
            return error("project_required", "project_id is required")
        try:
            record = get_project(project_id)
            state = load_project_state(record)
            if action == "list":
                records = asset_records(
                    Path(record.output),
                    project_id=record.project_id,
                    state=state,
                )
                used = [item for item in records if item.get("referenced")]
                unused = [item for item in records if not item.get("referenced")]
                return {
                    "ok": True,
                    "assets": records,
                    "used_assets": used,
                    "unused_workspace_files": unused,
                    "count": len(records),
                    "blocking": [
                        item for item in used if item.get("blocked")
                    ],
                }
            if action in {"approve", "quarantine"}:
                result = review_assets(
                    Path(record.output),
                    action=action,
                    project_id=record.project_id,
                    asset_ids=asset_ids,
                    license=license,
                    attribution=attribution,
                    reason=reason,
                )
                result["assets"] = asset_records(
                    Path(record.output),
                    project_id=record.project_id,
                    state=state,
                )
                return result
            return unknown_action(
                "vf_assets",
                action,
                ("list", "approve", "quarantine", "fonts", "register_font"),
            )
        except VideoFlowError as exc:
            return exc.to_dict()
