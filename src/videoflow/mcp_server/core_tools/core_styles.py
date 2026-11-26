"""VideoFlow core MCP tools: styles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.application.projects import get_project, load_project_state
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.context import error


def register(register: Any, ctx: Any, legacy: dict[str, Any]) -> None:
    @register
    def vf_style(
        action: str = "list",
        style_id: str = "",
        new_id: str = "",
        name: str = "",
        markdown_content: str = "",
        body: str = "",
        aspect_ratio: str | None = None,
        format_id: str | None = None,
        target_lufs: float | None = None,
        max_static_sec: float | None = None,
        min_silence_ms: int | None = None,
        layout_mode: str | None = None,
        caption_preset: str | None = None,
        motion_engine: str | None = None,
        platforms: list[str] | None = None,
        beatmap_defaults: dict[str, Any] | None = None,
        sound_design: dict[str, Any] | None = None,
        hook_strategy: str | None = None,
        intro_strategy: str | None = None,
        export_targets: list[str] | None = None,
        palette: list[str] | None = None,
        fonts: list[str] | None = None,
        cut_rhythm: dict[str, Any] | None = None,
        safe_zones: dict[str, Any] | None = None,
        reference_url: str = "",
        reference_dir: str = "",
        images: list[str] | None = None,
        workspace_dir: str = "",
        overwrite: bool = True,
        feedback_note: str = "",
        notes: list[str] | None = None,
        mode: str = "merge",
        max_rules: int = 15,
        project_id: str = "",
        duration_sec: float = 5.0,
    ) -> dict[str, Any]:
        """List, get, create, save, duplicate, restore, sync, or learn Markdown styles."""

        from videoflow.application import style_service
        from videoflow.domain.paths import resolve_allowed
        from videoflow.runtime import allowed_roots

        try:
            if workspace_dir:
                workspace_dir = str(resolve_allowed(Path(workspace_dir), allowed_roots()))
            if action == "list":
                sync = style_service.sync_styles(workspace_dir)["sync"] if workspace_dir else {}
                return {
                    "ok": True,
                    "styles": style_service.list_styles(),
                    "sync": sync,
                }
            if action == "analyze":
                if not (reference_url or reference_dir or images):
                    return error(
                        "reference_required",
                        "reference_url, reference_dir, or images is required",
                    )
                from videoflow.application.style_clone import clone_style
                from videoflow.runtime import portable_home

                output = Path(workspace_dir) if workspace_dir else portable_home()
                return clone_style(
                    style_id or name or "reference",
                    output,
                    reference_url=reference_url,
                    reference_dir=reference_dir,
                    images=images,
                    name=name,
                    save=False,
                )
            if action == "apply":
                if not project_id:
                    return error("project_required", "project_id is required")
                if not style_id:
                    return error("style_required", "style_id is required")
                from videoflow.application.style_compiler import apply_style

                return apply_style(project_id, style_id)
            if action == "preview":
                from videoflow.application.compositor import style_preview

                if not project_id:
                    return error("project_required", "project_id is required")
                if not style_id:
                    return error("style_required", "style_id is required")
                return style_preview(
                    project_id, style_id, duration_sec=duration_sec
                )
            if action == "get":
                return style_service.get_style(style_id)
            if action == "delete":
                return style_service.delete_style(style_id)
            if action == "duplicate":
                if not style_id:
                    return error("style_required", "style_id is required")
                return style_service.duplicate_style(
                    style_id,
                    new_id=new_id or f"{style_id}-copy",
                    name=name,
                )
            if action == "restore":
                if not style_id:
                    return error("style_required", "style_id is required")
                return style_service.restore_style(style_id)
            if action == "sync":
                if not workspace_dir:
                    return error("workspace_required", "workspace_dir is required")
                return style_service.sync_styles(workspace_dir, overwrite=overwrite)
            if action == "learn_rule":
                if not style_id:
                    return error("style_required", "style_id is required")
                rules = [str(item) for item in (notes or []) if str(item).strip()]
                if feedback_note.strip():
                    rules.append(feedback_note.strip())
                return style_service.learn_style(
                    style_id,
                    rules,
                    mode=mode,
                    max_rules=max_rules,
                    workspace_dir=workspace_dir or None,
                )
            if action not in {"save", "create", "update"}:
                return error("unknown_action", f"Unknown style action: {action}")
            if action == "create":
                overwrite = False
            if not style_id and not markdown_content.strip():
                return error("style_required", "style_id is required")
            updates = {
                key: value
                for key, value in (
                    ("body", body or None),
                    ("aspect_ratio", aspect_ratio),
                    ("format_id", format_id),
                    ("target_lufs", target_lufs),
                    ("max_static_sec", max_static_sec),
                    ("min_silence_ms", min_silence_ms),
                    ("layout_mode", layout_mode),
                    ("caption_preset", caption_preset),
                    ("motion_engine", motion_engine),
                    ("platforms", platforms),
                    ("beatmap_defaults", beatmap_defaults),
                    ("sound_design", sound_design),
                    ("hook_strategy", hook_strategy),
                    ("intro_strategy", intro_strategy),
                    ("export_targets", export_targets),
                    ("palette", palette),
                    ("fonts", fonts),
                    ("cut_rhythm", cut_rhythm),
                    ("safe_zones", safe_zones),
                )
                if value is not None
            }
            return style_service.save_style(
                style_id=style_id,
                name=name,
                markdown_content=markdown_content,
                updates=updates,
                overwrite=overwrite,
                workspace_dir=workspace_dir or None,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except ValueError as exc:
            return error("invalid_style", str(exc))

    @register
    def vf_style_validate(style_id: str) -> dict[str, Any]:
        """Validate one style without mutating its project."""

        from videoflow.application.style_catalog import StyleCatalog
        from videoflow.application.style_compiler import validate_style

        try:
            style = StyleCatalog().get(style_id)
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "style_id": style_id, "validation": validate_style(style)}

    @register
    def vf_style_apply(
        project_id: str,
        style_id: str,
        generate_beatmap: bool = True,
    ) -> dict[str, Any]:
        """Compile a style into parameters and a non-destructive beat-map draft."""

        from videoflow.application.style_compiler import apply_style

        try:
            return apply_style(
                project_id,
                style_id,
                generate_beatmap=generate_beatmap,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except ValueError as exc:
            return error("style_validation_failed", str(exc))

    @register
    def vf_beatmap_plan(
        project_id: str,
        style_id: str = "",
        instructions: str = "",
    ) -> dict[str, Any]:
        """Build a beat-map draft from the transcript and one style."""

        from videoflow.application.beatmap_plan import build_beatmap_plan, write_beatmap_plan
        from videoflow.application.style_catalog import StyleCatalog
        from videoflow.domain.styles import StyleDefinition

        try:
            record = get_project(project_id)
            state = load_project_state(record)
            identifier = style_id or record.style_id or state.style_id
            style = (
                StyleCatalog().get(identifier)
                if identifier
                else StyleDefinition(style_id="default", name="Default")
            )
            plan = build_beatmap_plan(state, style, instructions=instructions)
            path = write_beatmap_plan(Path(record.output), plan)
        except VideoFlowError as exc:
            return exc.to_dict()
        except ValueError as exc:
            return error("beatmap_plan_failed", str(exc))
        return {"ok": True, "project_id": project_id, "path": str(path), "plan": plan}
