"""Format preset MCP tool."""

from __future__ import annotations

from typing import Any

from videoflow.application.format_catalog import FormatCatalog
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.context import error


def register_format_tools(register: Any) -> None:
    @register
    def vf_format(
        action: str = "list",
        format_id: str = "",
        new_id: str = "",
        name: str = "",
        aspect_ratio: str = "9:16",
        width: int = 0,
        height: int = 0,
        fps: int = 0,
        safe_zones: dict[str, float] | None = None,
        caption_preset: str = "",
        platforms: list[str] | None = None,
        export_targets: list[str] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """List, get, save, delete, or duplicate output format presets."""

        selected = action.strip().lower()
        catalog = FormatCatalog()
        try:
            if selected == "list":
                return {"ok": True, "formats": catalog.list_payload()}
            if selected == "get":
                return {"ok": True, "format": catalog.get(format_id).model_dump(mode="json")}
            if selected == "delete":
                return {"ok": True, "deleted": catalog.delete(format_id)}
            if selected == "duplicate":
                item = catalog.duplicate(
                    format_id, new_id or f"{format_id}-copy", name=name
                )
                return {"ok": True, "format": item.model_dump(mode="json")}
            if selected not in {"save", "create", "update"}:
                return error(
                    "unknown_action",
                    "vf_format supports list, get, save, delete, or duplicate",
                )
            if not format_id:
                return error("format_required", "format_id is required")
            current = None
            if selected in {"save", "update"}:
                try:
                    current = catalog.get(format_id)
                except VideoFlowError:
                    current = None
            base = current.model_dump(mode="json") if current is not None else {}
            payload = {
                **base,
                "format_id": format_id,
                "name": name or base.get("name") or format_id,
                "aspect_ratio": aspect_ratio or base.get("aspect_ratio") or "9:16",
                "width": width or base.get("width") or 1080,
                "height": height or base.get("height") or 1920,
                "fps": fps or base.get("fps") or 30,
                "caption_preset": caption_preset
                or base.get("caption_preset")
                or "youtube_bold_yellow",
                "platforms": platforms if platforms is not None else base.get("platforms", []),
                "export_targets": (
                    export_targets
                    if export_targets is not None
                    else base.get("export_targets", [])
                ),
                "description": description or base.get("description", ""),
                "safe_zones": safe_zones
                if safe_zones is not None
                else base.get("safe_zones", {"bottom_px": 380.0, "right_px": 140.0}),
                "builtin": False,
            }
            from videoflow.domain.formats import FormatDefinition

            definition = FormatDefinition.model_validate(payload)
            path = catalog.save(definition)
            return {
                "ok": True,
                "format": definition.model_dump(mode="json"),
                "file": str(path),
            }
        except VideoFlowError as exc:
            return exc.to_dict()
        except ValueError as exc:
            return error("invalid_format", str(exc))


__all__ = ["register_format_tools"]
