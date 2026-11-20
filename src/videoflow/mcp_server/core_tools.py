"""Consolidated core MCP surface for VideoFlow.

Each tool owns one workflow area and exposes explicit ``action`` values. Legacy
single-purpose wrappers live only in the internal agent tool layer.
"""

from __future__ import annotations

import contextlib
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from vf_contracts.assets import iter_assets

from videoflow.application import artifacts as artifact_service
from videoflow.application.channel_kit import channel_kit_ids, is_channel_kit
from videoflow.application.hilt import list_requests, load_response, public_payload
from videoflow.application.projects import get_project, list_projects, load_project_state
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.agent_helpers import _job_payload
from videoflow.mcp_server.agent_tools import register_agent_tools
from videoflow.mcp_server.context import error
from videoflow.mcp_server.format_tools import register_format_tools
from videoflow.mcp_server.scene_tools import register_scene_tools
from videoflow.steps.registry import iter_steps


def _capture_legacy(register: Any, ctx: Any) -> dict[str, Any]:
    tools: dict[str, Any] = {}

    def capture(func: Any) -> Any:
        tools[func.__name__] = func
        return func

    register_agent_tools(capture, ctx)
    return tools


@lru_cache(maxsize=1)
def _step_catalog() -> tuple[dict[str, Any], ...]:
    """Build the static step catalog once per process."""

    return tuple(
        {
            "type": step.type,
            "title": step.title,
            "description": step.description,
            "status": step.status,
            "requires": list(step.requires),
            "produces": list(step.produces),
            "schema_resource": f"vf://docs/steps/{step.type}",
        }
        for step in iter_steps()
    )


def _is_step(step_type: str) -> bool:
    from videoflow.domain.errors import VideoFlowError
    from videoflow.steps.registry import get_step

    try:
        get_step(step_type)
        return True
    except VideoFlowError:
        return False


def _wait(manager: Any, project_id: str, job_id: str, timeout: float) -> dict[str, Any]:
    record = get_project(project_id)
    job = manager.get(job_id)
    if getattr(job, "project_id", "") not in {"", record.project_id}:
        return error("job_mismatch", "Job does not belong to this project")
    deadline = time.monotonic() + max(1.0, min(3600.0, timeout))
    terminal = {"succeeded", "failed", "cancelled", "answered", "needs_review"}
    while job.status not in terminal:
        if time.monotonic() >= deadline:
            return {"ok": False, "code": "timeout", "job": _job_payload(job)}
        heartbeat = getattr(manager, "heartbeat", None)
        if callable(heartbeat):
            with contextlib.suppress(Exception):
                heartbeat(job_id)
        time.sleep(0.5)
        job = manager.get(job_id)
    return {"ok": job.status == "succeeded", "job": _job_payload(job)}


def _fps_int(value: int | str | None) -> int | None:
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
        return number if number > 0 else None
    return None


def _short_clip_for_video(output: Path, video: Path) -> dict[str, Any] | None:
    """Find the Short manifest entry that owns ``video``."""

    import json

    target = Path(video).expanduser().resolve()
    for relative in (
        "shorts/batch/shorts_batch.json",
        "shorts/shorts_batch.json",
        "shorts.json",
    ):
        path = Path(output) / relative
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        clips = payload.get("clips") if isinstance(payload, dict) else None
        if not isinstance(clips, list):
            continue
        for clip in clips:
            if not isinstance(clip, dict) or not clip.get("path"):
                continue
            with contextlib.suppress(OSError):
                if Path(str(clip["path"])).expanduser().resolve() == target:
                    return clip
    return None


def register_core_tools(register: Any, ctx: Any) -> None:
    legacy = _capture_legacy(register, ctx)
    manager = ctx.manager

    @register
    def vf_style(
        action: str = "list",
        style_id: str = "",
        new_id: str = "",
        name: str = "",
        markdown_content: str = "",
        body: str = "",
        aspect_ratio: str | None = None,
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

    @register
    def vf_depth_composite(
        project_id: str,
        text_or_asset: str,
        start_sec: float,
        end_sec: float,
        style_props: dict[str, Any] | None = None,
        anchor: str = "center",
        width_ratio: float = 0.82,
    ) -> dict[str, Any]:
        """Place text/graphics behind a matted presenter in one time range."""

        from videoflow.application.compositor import depth_composite

        try:
            return depth_composite(
                project_id,
                text_or_asset,
                start_sec,
                end_sec,
                style_props=style_props,
                anchor=anchor,
                width_ratio=width_ratio,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except (OSError, ValueError) as exc:
            return error("depth_composite_failed", str(exc))

    @register
    def vf_pip(
        project_id: str,
        overlay_asset: str,
        start_sec: float,
        end_sec: float,
        anchor: str = "bottom_right",
        corner_radius: int = 24,
        width_ratio: float = 0.28,
        margin_x: int = 32,
        margin_y: int = 32,
        z: int = 25,
    ) -> dict[str, Any]:
        """Add a rounded-window picture-in-picture overlay."""

        from videoflow.application.compositor import picture_in_picture

        try:
            return picture_in_picture(
                project_id,
                overlay_asset,
                start_sec,
                end_sec,
                anchor=anchor,
                corner_radius=corner_radius,
                width_ratio=width_ratio,
                margin_x=margin_x,
                margin_y=margin_y,
                z=z,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except (OSError, ValueError) as exc:
            return error("pip_failed", str(exc))

    @register
    def vf_parallax(
        project_id: str,
        image_path: str,
        start_sec: float,
        end_sec: float,
        bg_scale: float = 1.04,
        fg_scale: float = 1.12,
        rotate_y_deg: float = 3.0,
        width_ratio: float = 0.72,
        z: int = 10,
    ) -> dict[str, Any]:
        """Animate a still as background plus subject 2.5D parallax."""

        from videoflow.application.compositor import parallax

        try:
            return parallax(
                project_id,
                image_path,
                start_sec,
                end_sec,
                bg_scale=bg_scale,
                fg_scale=fg_scale,
                rotate_y_deg=rotate_y_deg,
                width_ratio=width_ratio,
                z=z,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except (OSError, ValueError) as exc:
            return error("parallax_failed", str(exc))

    @register
    def vf_style_preview(
        project_id: str,
        style_id: str,
        duration_sec: float = 5.0,
    ) -> dict[str, Any]:
        """Render a short style card with palette, font, layout, and caption."""

        from videoflow.application.compositor import style_preview

        try:
            return style_preview(project_id, style_id, duration_sec=duration_sec)
        except VideoFlowError as exc:
            return exc.to_dict()
        except (OSError, ValueError) as exc:
            return error("style_preview_failed", str(exc))

    @register
    def vf_shorts_batch(
        project_id: str,
        clips: list[dict[str, Any]],
        wait: bool = True,
    ) -> dict[str, Any]:
        """Render several Shorts in one batch with per-clip settings."""

        try:
            record = get_project(project_id)
        except VideoFlowError as exc:
            return exc.to_dict()
        job = manager.start(
            Path(record.primary_source or record.output),
            Path(record.output),
            {
                "mode": "shorts_batch",
                "project_id": record.project_id,
                "clips": clips,
            },
            queue=True,
            project_id=record.project_id,
        )
        response: dict[str, Any] = {
            "ok": True,
            "project_id": project_id,
            "job": _job_payload(job),
        }
        if wait:
            response["wait"] = _wait(manager, project_id, str(job.job_id), 1800.0)
        return response

    @register
    def vf_qa_final(
        project_id: str,
        video_path: str = "",
        strict: bool = True,
        platforms: list[str] | None = None,
        mode: str = "full",
        collision_mode: str = "visual",
        max_wer: float = 0.12,
    ) -> dict[str, Any]:
        """Audit the deliverable MP4 and write a contact sheet."""

        from videoflow.application.qa_final import audit_final
        from videoflow.application.shorts import short_dimensions

        try:
            record = get_project(project_id)
            state = load_project_state(record)
            output = Path(record.output)
            default = output / "exports" / "youtube_master.mp4"
            fallback = output / "exports" / "final_youtube.mp4"
            video = (
                Path(video_path).expanduser()
                if video_path
                else (default if default.is_file() else fallback)
            )
            clip = _short_clip_for_video(output, video)
            if clip is None:
                import json

                bundle_fps: int | None = None
                bundle_frames: int | None = None
                bundle_path = output / "exports" / "bundle.json"
                try:
                    bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
                    bundle_fps = _fps_int(
                        (bundle_payload.get("mp4") or {}).get("fps")
                    )
                    frames = bundle_payload.get("mp4_frames")
                    bundle_frames = int(frames) if frames else None
                except (OSError, ValueError, TypeError):
                    pass
                report = audit_final(
                    video,
                    output=output,
                    state=state,
                    strict=strict,
                    platforms=platforms,
                    mode=mode,
                    fps=float(bundle_fps) if bundle_fps else None,
                    expected_frames=bundle_frames,
                    collision_mode=collision_mode,
                    max_wer=max_wer,
                )
            else:
                start = float(clip.get("start_sec") or 0.0)
                end = float(clip.get("end_sec") or start)
                aspect = str(clip.get("aspect_ratio") or "9:16")
                clip_width, clip_height = short_dimensions(aspect)
                rate = state.media_info.audio_sample_rate if state.media_info else 48000
                transcript = [
                    item
                    for item in state.transcript
                    if item.end_sample > round(start * rate)
                    and item.start_sample < round(end * rate)
                    and item.id not in set(state.pipeline.discard_sentence_ids)
                ]
                subtitles = str(clip.get("subtitles") or "")
                subtitle_path = Path(subtitles).expanduser() if subtitles else None
                if subtitle_path is not None and not subtitle_path.is_absolute():
                    subtitle_path = output / subtitle_path
                report = audit_final(
                    video,
                    output=output,
                    state=state,
                    strict=strict,
                    platforms=platforms,
                    mode=mode,
                    window_sec=(start, end),
                    expected_sec=max(0.0, end - start),
                    fps=float(clip.get("fps") or 30.0),
                    transcript=transcript,
                    caption_path=subtitle_path,
                    width=clip_width,
                    height=clip_height,
                    collision_mode=collision_mode,
                    max_wer=max_wer,
                )
                report["short"] = {
                    "title": clip.get("title", ""),
                    "start_sec": start,
                    "end_sec": end,
                    "aspect_ratio": aspect,
                }
        except (VideoFlowError, OSError, ValueError) as exc:
            return error("qa_final_failed", str(exc))
        return {"ok": bool(report.get("ok")), "report": report}

    @register
    def vf_qa_compare(
        project_id: str,
        report_a: str,
        report_b: str,
    ) -> dict[str, Any]:
        """Compare two immutable QA reports for regressions."""

        from videoflow.application.qa_store import QaStore

        if not report_a or not report_b:
            return error("qa_reports_required", "report_a and report_b are required")
        try:
            record = get_project(project_id)
            output = Path(record.output)

            def resolve(value: str) -> Path:
                path = Path(value).expanduser()
                return path if path.is_absolute() else output / path

            return QaStore(output).compare(resolve(report_a), resolve(report_b))
        except VideoFlowError as exc:
            return exc.to_dict()

    @register
    def vf_glossary(
        action: str = "list",
        channel_id: str = "",
        terms: list[dict[str, Any]] | None = None,
        text: str = "",
    ) -> dict[str, Any]:
        """List, update, or apply a channel glossary of technical terms."""

        from videoflow.application.glossary import (
            apply_glossary,
            load_glossary,
            upsert_glossary,
        )

        try:
            if action == "list":
                return load_glossary(channel_id)
            if action == "upsert":
                return upsert_glossary(channel_id, list(terms or []))
            if action == "apply":
                corrected, count = apply_glossary(
                    text, load_glossary(channel_id)["terms"]
                )
                return {
                    "ok": True,
                    "channel_id": channel_id,
                    "text": corrected,
                    "applied": count,
                }
            return error(
                "unknown_action",
                "vf_glossary supports list, upsert, or apply",
            )
        except (OSError, ValueError) as exc:
            return error("glossary_failed", str(exc))

    @register
    def vf_preflight_plan(
        project_id: str,
        operation: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Validate schema, dependencies, licenses, disk, GPU, and cost."""

        from videoflow.application.preflight_plan import build_preflight_plan

        try:
            return build_preflight_plan(project_id, operation, params)
        except VideoFlowError as exc:
            return exc.to_dict()
        except (OSError, ValueError) as exc:
            return error("preflight_failed", str(exc))

    @register
    def vf_transcript_query(
        project_id: str,
        query: str = "",
        source_id: str = "",
        start_sec: float = 0.0,
        end_sec: float = 0.0,
        sentence_range: str = "",
        include_words: bool = False,
        limit: int = 50,
        cursor: int = 0,
    ) -> dict[str, Any]:
        """Search or page through the cleaned transcript without dumping it."""

        try:
            record = get_project(project_id)
            state = load_project_state(record)
        except VideoFlowError as exc:
            return exc.to_dict()
        rate = (
            state.media_info.audio_sample_rate
            if state.media_info is not None
            else 48000
        )
        start_sample = round(max(0.0, float(start_sec)) * rate) if start_sec else 0
        end_sample = round(max(0.0, float(end_sec)) * rate) if end_sec else 0
        range_start = range_end = None
        if sentence_range:
            try:
                left, right = sentence_range.replace(":", "-").split("-", 1)
                range_start = int(left)
                range_end = int(right)
            except (TypeError, ValueError):
                return error(
                    "invalid_sentence_range",
                    "sentence_range must look like '30-50'",
                )
        text_query = str(query or "").strip().casefold()
        discarded = set(state.pipeline.discard_sentence_ids)
        selected = []
        for sentence in state.transcript:
            if sentence.id in discarded:
                continue
            if range_start is not None and not (range_start <= sentence.id <= range_end):
                continue
            if start_sample and sentence.end_sample <= start_sample:
                continue
            if end_sample and sentence.start_sample >= end_sample:
                continue
            if text_query and text_query not in sentence.text.casefold():
                continue
            selected.append(sentence)
        page_size = max(1, min(int(limit), 200))
        offset = max(0, int(cursor))
        page = selected[offset : offset + page_size]
        items = []
        for sentence in page:
            item: dict[str, Any] = {
                "id": sentence.id,
                "start": round(sentence.start_sample / rate, 3),
                "end": round(sentence.end_sample / rate, 3),
                "text": sentence.text,
                "speaker": sentence.speaker,
            }
            if include_words:
                item["words"] = [
                    {
                        "word": word.word,
                        "start": round(word.start_sample / rate, 3),
                        "end": round(word.end_sample / rate, 3),
                        "probability": round(word.probability, 3),
                    }
                    for word in sentence.words
                ]
            items.append(item)
        next_cursor = offset + page_size if offset + page_size < len(selected) else None
        result: dict[str, Any] = {
            "ok": True,
            "project_id": project_id,
            "count": len(selected),
            "returned": len(items),
            "cursor": offset,
            "next_cursor": next_cursor,
            "sentences": items,
        }
        if source_id:
            result["warning"] = "source_id is not attached to transcript sentences yet"
        return result

    @register
    def vf_storyboard_strip(
        project_id: str,
        source_id: str = "",
        start_sec: float = 0.0,
        end_sec: float = 0.0,
        cols: int = 5,
        annotate: bool = True,
    ) -> dict[str, Any]:
        """Render a 5x2 contact sheet of one timeline/source range."""

        from videoflow.application.storyboard_strip import build_storyboard_strip

        try:
            record = get_project(project_id)
            state = load_project_state(record)
            media = state.source_media(source_id) if source_id else state.media_info
            source = Path(
                media.source_path if media is not None else record.primary_source
            )
            if not source.is_file():
                return error("source_not_found", f"Source is missing: {source}")
            result = build_storyboard_strip(
                source,
                record.output,
                start_sec=start_sec,
                end_sec=end_sec,
                cols=cols,
                annotate=annotate,
            )
            return {"ok": True, "project_id": project_id, "storyboard": result}
        except VideoFlowError as exc:
            return exc.to_dict()
        except (OSError, ValueError) as exc:
            return error("storyboard_failed", str(exc))

    @register
    def vf_gpu_preflight(require_gpu: bool = False) -> dict[str, Any]:
        """Validate the Windows GPU worker before a long job."""

        from videoflow.application.compute import router_from_settings
        from videoflow.application.settings import load_settings

        try:
            settings = load_settings()
            router = router_from_settings(settings)
            health = router.health(force=True)
            probe: dict[str, Any] = {}
            if health.available:
                try:
                    probe = router.client.probe()
                except Exception:  # noqa: BLE001 - probe is advisory
                    probe = {}
            if not health.available and require_gpu:
                return error(
                    "gpu_worker_unreachable",
                    "Windows GPU worker is not reachable.",
                    fix_hint="Start the worker on Windows or switch compute mode to local.",
                    worker_url=router.worker_url,
                    health=health.model_dump(mode="json"),
                )
            return {
                "ok": True,
                "remote_available": bool(health.available),
                "degraded": not bool(health.available),
                "degraded_reason": (
                    "" if health.available else "windows_gpu_offline_fallback_cpu"
                ),
                "mode": router.mode,
                "transport": getattr(router, "transport", "auto"),
                "worker_url": router.worker_url,
                "health": health.model_dump(mode="json"),
                "probe": probe,
            }
        except Exception as exc:  # noqa: BLE001 - preflight must return a payload
            if require_gpu:
                return error(
                    "gpu_worker_unreachable",
                    str(exc),
                    fix_hint="Check the GPU settings and worker status.",
                )
            return {
                "ok": True,
                "remote_available": False,
                "degraded": True,
                "degraded_reason": f"gpu_preflight_failed: {exc}",
                "mode": "local",
                "transport": "auto",
                "worker_url": "",
                "health": {},
                "probe": {},
            }

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

        from videoflow.application.assets_service import (
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
            return error(
                "unknown_action",
                "vf_assets supports list, approve, quarantine, fonts, or register_font",
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
            return error(
                "unknown_action",
                "vf_assets supports list, approve, quarantine, fonts, or register_font",
            )
        except VideoFlowError as exc:
            return exc.to_dict()

    @register
    def vf_project(
        action: str = "status",
        project_id: str = "",
        name: str = "",
        output: str = "",
        sources: list[str] | None = None,
        channel_id: str = "",
        style_id: str = "",
        reference_url: str = "",
        reference_dir: str = "",
        images: list[str] | None = None,
        notes: list[str] | None = None,
        mode: str = "merge",
        max_rules: int = 15,
        revision_id: str = "",
        label: str = "",
        force: bool = False,
        status: str = "",
        include_archived: bool = False,
        target_project_id: str = "",
    ) -> dict[str, Any]:
        """Create/open/status a project, manage lifecycle, or undo revisions."""

        if action == "session_brief":
            from videoflow.application.session_brief import build_session_brief

            try:
                return build_session_brief(project_id)
            except VideoFlowError as exc:
                return exc.to_dict()
        if action in {"checkpoint", "checkpoints", "restore_checkpoint"}:
            from videoflow.application.session_brief import (
                create_checkpoint,
                list_checkpoints,
                restore_checkpoint,
            )

            try:
                if action == "checkpoint":
                    return create_checkpoint(project_id, label)
                if action == "checkpoints":
                    return list_checkpoints(project_id)
                return restore_checkpoint(project_id, label)
            except VideoFlowError as exc:
                return exc.to_dict()
        if action == "list":
            from videoflow.application.projects import project_disk_size

            items = []
            for item in list_projects():
                if not include_archived and item.status == "archived":
                    continue
                if status and item.status != status:
                    continue
                items.append({**item.to_dict(), "size_bytes": project_disk_size(item)})
            return {"ok": True, "projects": items}
        if action in {"archive", "unarchive"}:
            from videoflow.application.projects import archive_project

            try:
                item = archive_project(get_project(project_id), archived=action == "archive")
            except VideoFlowError as exc:
                return exc.to_dict()
            return {"ok": True, "project": item.to_dict()}
        if action == "delete":
            from videoflow.application.projects import delete_project

            try:
                record = get_project(project_id)
                active = [
                    job
                    for job in manager.list()
                    if job.project_id == record.project_id
                    and job.status
                    not in {
                        "succeeded",
                        "failed",
                        "cancelled",
                        "answered",
                    }
                ]
                if active:
                    return error(
                        "project_busy",
                        "Cancel active jobs before deleting the project",
                        jobs=[str(job.job_id) for job in active],
                    )
                report = delete_project(record, force=force)
            except VideoFlowError as exc:
                return exc.to_dict()
            return {"ok": True, **report}
        if action in {"history", "undo", "restore"}:
            from videoflow.application import revisions
            from videoflow.application.projects import save_project_state

            try:
                record = get_project(project_id)
                if action == "history":
                    return {
                        "ok": True,
                        "revisions": revisions.list_snapshots(record.output),
                        "current_revision": record.revision,
                    }
                identifier = revision_id or revisions.latest_snapshot(record.output)
                restored = revisions.load_snapshot(record.output, identifier).model_copy(
                    update={"revision": record.revision}
                )
                saved = save_project_state(
                    record,
                    restored,
                    bump_revision=True,
                    snapshot=True,
                    snapshot_reason=f"before_{action}",
                    snapshot_step=action,
                )
            except VideoFlowError as exc:
                return exc.to_dict()
            return {
                "ok": True,
                "project_id": project_id,
                "revision_id": identifier,
                "revision": saved.revision,
                "resources": {
                    "state": f"vf://projects/{project_id}/state",
                    "timeline": f"vf://projects/{project_id}/timeline",
                },
            }
        if action == "clone":
            from videoflow.application.projects import clone_project

            try:
                cloned, state = clone_project(
                    get_project(project_id),
                    name=name,
                    output=output,
                    project_id=target_project_id,
                )
            except VideoFlowError as exc:
                return exc.to_dict()
            return {
                "ok": True,
                "project": cloned.to_dict(),
                "revision": state.revision,
                "resources": {
                    "state": f"vf://projects/{cloned.project_id}/state",
                    "timeline": f"vf://projects/{cloned.project_id}/timeline",
                },
            }
        if action in {"clone_style", "learn_rule"}:
            from videoflow.application.style_clone import clone_style, learn_rule

            if not channel_id:
                return error("channel_required", "channel_id is required")
            try:
                record = get_project(project_id) if project_id else None
                base = Path(record.output) if record is not None else Path(output).expanduser()
                if record is None and not output:
                    return error(
                        "output_required",
                        "Pass project_id or output for style learning",
                    )
                if action == "clone_style":
                    return clone_style(
                        channel_id,
                        base,
                        reference_url=reference_url,
                        reference_dir=reference_dir,
                        images=images,
                        name=name,
                    )
                return learn_rule(
                    channel_id,
                    base,
                    notes=notes,
                    mode=mode,
                    max_rules=max_rules,
                )
            except VideoFlowError as exc:
                return exc.to_dict()
        if action in {"init", "open"}:
            if channel_id and not is_channel_kit(channel_id):
                return error(
                    "channel_not_found",
                    f"Unknown channel kit: {channel_id}. Use one of: "
                    + ", ".join(channel_kit_ids())
                    + ". Styles belong in style_id.",
                )
            if style_id:
                from videoflow.application.style_catalog import StyleCatalog

                try:
                    StyleCatalog().get(style_id)
                except VideoFlowError as exc:
                    return exc.to_dict()
            return legacy["vf_project_init"](
                project_id=project_id,
                name=name,
                output=output,
                sources=sources,
                channel_id=channel_id,
                style_id=style_id,
            )
        if not project_id:
            return error("project_required", "project_id is required")
        return legacy["vf_project_status"](project_id=project_id)

    @register
    def vf_capabilities(allow_external_services: bool = False) -> dict[str, Any]:
        """Backends, models, and external-provider policy."""

        payload = legacy["vf_capabilities"](allow_external_services=allow_external_services)
        from videoflow.application.compute import compute_status
        from videoflow.application.models import model_diagnostics

        payload["models"] = model_diagnostics()
        payload["compute"] = compute_status()
        return payload

    @register
    def vf_catalog_search(
        query: str = "",
        kind: str = "steps",
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List or search the node/tool catalog without loading schemas."""

        if kind not in {"all", "steps"}:
            return error(
                "invalid_kind",
                "kind must be 'steps' or 'all'; MCP does not expose recipes",
            )
        needle = query.strip().casefold()
        cap = max(1, min(200, int(limit)))
        start = max(0, int(offset))
        matches = [
            step
            for step in _step_catalog()
            if not needle
            or needle in f"{step['type']} {step['title']} {step['description']}".casefold()
        ]
        page = matches[start : start + cap]
        next_offset = start + len(page)
        return {
            "ok": True,
            "query": query,
            "steps": page,
            "total": len(matches),
            "offset": start,
            "limit": cap,
            "next_offset": next_offset if next_offset < len(matches) else None,
        }

    @register
    def vf_exec(
        action: str = "step",
        project_id: str = "",
        step_id: str = "",
        params: dict[str, Any] | None = None,
        source: str = "",
        wait: bool = False,
        timeout_sec: float = 300.0,
        short_index: int = 0,
        short_title: str = "",
        short_start_sec: float | None = None,
        short_end_sec: float | None = None,
        aspect_ratio: str = "",
        burn_subtitles: bool | None = None,
        caption_style: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run one catalog step or edit one Short in a project."""

        try:
            record = get_project(project_id)
        except VideoFlowError as exc:
            return exc.to_dict()
        if action == "short":
            return legacy["vf_edit_short"](
                project_id=project_id,
                index=short_index,
                title=short_title or None,
                start_sec=short_start_sec,
                end_sec=short_end_sec,
                aspect_ratio=aspect_ratio or None,
                burn_subtitles=burn_subtitles,
                caption_style=caption_style,
            )
        if action == "step":
            if not step_id:
                return error("step_required", "step_id is required")
            from videoflow.steps.registry import get_step

            try:
                get_step(step_id)
            except VideoFlowError as exc:
                return exc.to_dict()
            source_path = Path(source or record.primary_source or record.output)
            job = manager.start(
                source_path,
                Path(record.output),
                {
                    "mode": "step",
                    "project_id": record.project_id,
                    "step_type": step_id,
                    "params": dict(params or {}),
                },
                queue=True,
                project_id=record.project_id,
            )
            response = {"ok": True, "job": _job_payload(job), "project_id": project_id}
        else:
            return error(
                "unknown_action",
                "vf_exec supports action='step' or action='short'; recipes are not exposed via MCP",
            )
        if wait and response.get("ok"):
            job_id = str((response.get("job") or {}).get("job_id") or "")
            if job_id:
                waited = _wait(manager, project_id, job_id, timeout_sec)
                response["wait"] = waited
        return response

    @register
    def vf_run(
        project_id: str,
        steps: list[str] | str,
        through: str | None = None,
        params: dict[str, Any] | None = None,
        resume: bool = True,
        wait: bool = True,
        timeout_sec: float = 1800.0,
    ) -> dict[str, Any]:
        """Run an ordered linear chain of catalog steps sharing one context."""

        try:
            record = get_project(project_id)
        except VideoFlowError as exc:
            return exc.to_dict()
        requested: list[str] = []
        if isinstance(steps, str):
            raw = [item.strip() for item in steps.split(",") if item.strip()]
            if len(raw) == 1 and not _is_step(raw[0]):
                from videoflow.application.workflow_catalog import WorkflowCatalog

                try:
                    workflow = WorkflowCatalog().get(raw[0])
                except VideoFlowError as exc:
                    return exc.to_dict()
                requested = [step.node for step in workflow.steps]
            else:
                requested = raw
        else:
            requested = [str(item).strip() for item in steps if str(item).strip()]
        if not requested:
            return error("steps_required", "Pass at least one step type")
        missing = [item for item in requested if not _is_step(item)]
        if missing:
            return error(
                "unknown_step",
                "Unknown or non-linear nodes: " + ", ".join(missing),
                steps=missing,
            )
        if through and through not in requested:
            return error("through_not_in_steps", "through must be one of the requested steps")
        job = manager.start(
            Path(record.primary_source or record.output),
            Path(record.output),
            {
                "mode": "run",
                "project_id": record.project_id,
                "steps": requested,
                "through": through or "",
                "params": dict(params or {}),
                "resume": bool(resume),
            },
            queue=True,
            project_id=record.project_id,
        )
        response: dict[str, Any] = {
            "ok": True,
            "project_id": project_id,
            "steps": requested,
            "job": _job_payload(job),
        }
        if wait:
            response["wait"] = _wait(manager, project_id, str(job.job_id), timeout_sec)
        return response

    @register
    def vf_job(
        action: str = "get",
        project_id: str = "",
        job_id: str = "",
        step_id: str = "",
        tail_lines: int = 100,
        timeout_sec: float = 300.0,
        limit: int = 20,
        force: bool = False,
        status: str = "",
        include_images: bool = False,
    ) -> dict[str, Any]:
        """List, cancel, get, wait, inspect logs, or read QA for a job."""

        from videoflow.application import database

        if action == "list":
            cap = max(1, min(200, int(limit)))
            stored = database.list_jobs(
                status=status,
                project_id=project_id,
                limit=cap,
            )
            local = [
                job.to_dict(summary=True)
                for job in manager.list(limit=cap)
                if (not project_id or job.project_id == project_id)
                and (not status or job.status == status)
            ]
            merged: dict[str, dict[str, Any]] = {
                str(item.get("job_id")): item for item in stored if item.get("job_id")
            }
            for item in local:
                merged.setdefault(str(item.get("job_id")), item)
            jobs = sorted(
                merged.values(),
                key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
                reverse=True,
            )[:cap]
            return {"ok": True, "jobs": jobs, "total": len(merged)}
        if action == "cancel":
            if not job_id:
                return error("job_required", "job_id is required")
            stored = []
            try:
                stored = database.list_jobs(job_id=job_id, limit=1)
            except Exception:  # noqa: BLE001 - DB is advisory for local jobs
                stored = []
            try:
                job = manager.cancel(job_id, force=force)
                payload = job.to_dict(summary=True)
            except VideoFlowError:
                payload = stored[0] if stored else {}
            database.request_job_cancel(job_id, force=force)
            if not payload:
                return error("job_not_found", f"Unknown job: {job_id}")
            return {"ok": True, "job": payload, "cancelled": True}
        if action == "logs":
            return legacy["vf_get_step_logs"](
                project_id=project_id,
                job_id=job_id,
                step_id=step_id,
                tail_lines=tail_lines,
            )
        if action == "qa":
            return legacy["vf_get_qa_artifacts"](
                project_id=project_id, include_images=include_images
            )[0]
        if action == "wait":
            try:
                return _wait(manager, project_id, job_id, timeout_sec)
            except VideoFlowError as exc:
                return exc.to_dict()
        if action == "status":
            try:
                return {"ok": True, "job": _job_payload(manager.get(job_id))}
            except VideoFlowError:
                stored = database.list_jobs(job_id=job_id, limit=1)
                if not stored:
                    return error("job_not_found", f"Unknown job: {job_id}")
                return {"ok": True, "job": stored[0]}
        if action == "get":
            return legacy["vf_get_job"](project_id=project_id, job_id=job_id)
        return error(
            "unknown_action",
            "vf_job supports list, cancel, get, status, wait, logs, or qa",
        )

    @register
    def vf_timeline(
        action: str = "get",
        project_id: str = "",
        job_id: str = "",
        clip_id: str = "",
        edit_action: str = "trim",
        start_sec: float | None = None,
        end_sec: float | None = None,
        delta_sec: float = 0.0,
        split_sec: float | None = None,
        expected_revision: int | None = None,
        beatmap: dict[str, Any] | None = None,
        time_basis: str = "timeline",
        keep_ranges: list[dict[str, Any]] | None = None,
        remove_ranges: list[dict[str, Any]] | None = None,
        sentence_ids: list[int] | None = None,
        dry_run: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        """Read, edit, discard sentences, or apply a declarative beatmap."""

        if action == "discard_sentences":
            if not sentence_ids:
                return error("sentence_ids_required", "sentence_ids is required")
            from videoflow.application.projects import save_project_state

            try:
                record = get_project(project_id)
                state = load_project_state(record)
                discarded = set(state.pipeline.discard_sentence_ids)
                discarded.update(int(item) for item in sentence_ids)
                updated = state.model_copy(
                    update={
                        "pipeline": state.pipeline.model_copy(
                            update={"discard_sentence_ids": sorted(discarded)}
                        )
                    }
                )
                saved = save_project_state(
                    record,
                    updated,
                    expected_revision=expected_revision,
                    bump_revision=True,
                    snapshot=True,
                    snapshot_reason="discard_sentences",
                    snapshot_step="discard_sentences",
                )
                return {
                    "ok": True,
                    "project_id": project_id,
                    "discarded_sentence_ids": sorted(discarded),
                    "revision": saved.revision,
                }
            except VideoFlowError as exc:
                return exc.to_dict()
        if action == "apply_beatmap":
            from videoflow.application.beatmap import (
                BeatmapError,
                apply_beatmap,
                write_beatmap_sidecar,
            )
            from videoflow.application.projects import save_project_state

            if not beatmap and not keep_ranges and not remove_ranges:
                return error("beatmap_required", "Pass a beatmap manifest or ranges")
            if time_basis not in {"timeline", "source"}:
                return error("invalid_time_basis", "time_basis must be timeline or source")
            manifest = dict(beatmap or {})
            if keep_ranges is not None:
                manifest["keep_ranges"] = keep_ranges
            if remove_ranges is not None:
                manifest["remove_ranges"] = remove_ranges
            manifest["time_basis"] = time_basis
            try:
                record = get_project(project_id)
                state = load_project_state(record)
                updated, report, sidecar = apply_beatmap(
                    state,
                    Path(record.output),
                    manifest,
                    expected_revision=expected_revision,
                    time_basis=time_basis,  # type: ignore[arg-type]
                    dry_run=dry_run,
                    force=force,
                )
                if dry_run:
                    return {
                        "ok": True,
                        "dry_run": True,
                        "revision": state.revision,
                        "report": report.to_dict(),
                        "sidecar": "",
                    }
                saved = save_project_state(
                    record,
                    updated,
                    expected_revision=expected_revision,
                    bump_revision=True,
                    snapshot=True,
                    snapshot_reason="apply_beatmap",
                    snapshot_step="apply_beatmap",
                )
                sidecar_path = ""
                if sidecar.get("sfx_events") or sidecar.get("music_tracks"):
                    sidecar_path = str(write_beatmap_sidecar(Path(record.output), sidecar))
                return {
                    "ok": True,
                    "revision": saved.revision,
                    "report": report.to_dict(),
                    "sidecar": sidecar_path,
                }
            except BeatmapError as exc:
                return {
                    "ok": False,
                    "code": "beatmap_conflict",
                    "message": str(exc),
                    "report": exc.report.to_dict(),
                }
            except ValueError as exc:
                return error("invalid_beatmap_range", str(exc))
            except VideoFlowError as exc:
                return exc.to_dict()
        if action == "edit":
            if time_basis == "source":
                from videoflow.application.time_map import source_to_timeline_sec

                try:
                    state = load_project_state(get_project(project_id))
                    if start_sec is not None:
                        start_sec = source_to_timeline_sec(state, start_sec)
                    if end_sec is not None:
                        end_sec = source_to_timeline_sec(state, end_sec)
                    if split_sec is not None:
                        split_sec = source_to_timeline_sec(state, split_sec)
                except VideoFlowError as exc:
                    return exc.to_dict()
                except ValueError as exc:
                    return error("time_outside_timeline", str(exc))
            elif time_basis != "timeline":
                return error("invalid_time_basis", "time_basis must be timeline or source")
            return legacy["vf_edit_timeline"](
                project_id=project_id,
                clip_id=clip_id,
                action=edit_action,
                start_sec=start_sec,
                end_sec=end_sec,
                delta_sec=delta_sec,
                split_sec=split_sec,
                expected_revision=expected_revision,
            )
        return legacy["vf_get_timeline"](project_id=project_id, job_id=job_id)

    @register
    def vf_artifact(
        action: str = "list",
        project_id: str = "",
        artifact: str = "",
        include_content: bool = True,
    ) -> Any:
        """List or get project artifacts and image content."""

        if action == "list":
            try:
                record = get_project(project_id)
            except VideoFlowError as exc:
                return exc.to_dict()
            workspace_assets = [item.model_dump(mode="json") for item in iter_assets(project_id)]
            return {
                "ok": True,
                "artifacts": [
                    *artifact_service.list_artifacts(Path(record.output)),
                    *workspace_assets,
                ],
            }
        cached = next(
            (
                asset
                for asset in iter_assets(project_id)
                if artifact in {asset.asset_id, asset.path, Path(asset.path).name}
            ),
            None,
        )
        if cached is not None:
            path = Path(cached.path)
            if not path.is_absolute():
                from vf_contracts.workspace import project_dir

                path = project_dir(project_id) / path
            result: list[Any] = [{"ok": True, **cached.model_dump(mode="json")}]
            if include_content and cached.kind in {"images", "graphics"} and path.is_file():
                from mcp.server.mcpserver import Image

                result.append(Image(path=str(path)))
            return result
        return legacy["vf_get_artifact"](
            project_id=project_id,
            artifact=artifact,
            include_content=include_content,
        )

    def _run_bundle(
        project_id: str,
        *,
        targets: str | list[str] | None = None,
        look: dict[str, Any] | None = None,
        audio_source: str = "master",
        captions: bool = True,
        draft: bool = False,
        dialect: str = "1.10",
        mp4_profile: str = "youtube_h264",
        mp4_loudness_lufs: float | None = -16.5,
        fps: int | str = 30,
        qa_mode: str = "fast",
        mp4_preset: str = "veryfast",
    ) -> dict[str, Any]:
        from videoflow.application.delivery_bundle import (
            DEFAULT_BUNDLE_TARGETS,
            DeliveryBundleRequest,
            build_delivery_bundle,
        )

        requested = [targets] if isinstance(targets, str) else targets
        record = get_project(project_id)
        state = load_project_state(record)
        if not state.video_segments:
            from videoflow.application.delivery_bundle import TimelineRequiredError

            raise TimelineRequiredError("Project has no built timeline")
        if not requested:
            style_id = record.style_id or record.channel_id
            if style_id:
                from videoflow.application.style_catalog import StyleCatalog
                from videoflow.domain.errors import StyleNotFoundError

                try:
                    requested = StyleCatalog().get(style_id).export_targets
                except StyleNotFoundError:
                    requested = None
        requested = requested or list(DEFAULT_BUNDLE_TARGETS)
        if record.channel_id:
            from videoflow.application.brand_kit import load_brand_kit

            brand = load_brand_kit(record.channel_id)
            if brand.get("lut"):
                merged = dict(look or {})
                merged.setdefault("lut_path", str(brand["lut"]))
                look = merged
        bundle = build_delivery_bundle(
            state,
            Path(record.output),
            request=DeliveryBundleRequest(
                targets=tuple(requested),
                dialect=dialect,  # type: ignore[arg-type]
                mp4_profile=mp4_profile,
                mp4_loudness_lufs=mp4_loudness_lufs,
                burn_subtitles=captions,
                audio_source=audio_source,
                look=look,
                mp4_draft=draft,
                mp4_fps=fps,
                mp4_preset=mp4_preset,
            ),
        )
        mp4 = (bundle.get("files") or {}).get("mp4") or {}
        path = Path(str(mp4.get("path") or ""))
        if not draft and qa_mode != "off" and path.is_file():
            from videoflow.application.qa_final import audit_final

            if qa_mode == "fast":
                report = audit_final(
                    path,
                    output=Path(record.output),
                    state=state,
                    strict=True,
                    mode="fast",
                    fps=_fps_int(fps),
                    expected_frames=bundle.get("mp4_frames"),
                )
                bundle["qa_final"] = report
                bundle["ok"] = bool(bundle.get("ok")) and bool(report.get("ok"))
            elif qa_mode == "full":
                job = manager.start(
                    Path(record.primary_source or record.output),
                    Path(record.output),
                    {
                        "mode": "qa_full",
                        "project_id": record.project_id,
                        "video_path": str(path),
                        "fps": _fps_int(fps),
                        "expected_frames": bundle.get("mp4_frames"),
                    },
                    queue=True,
                    project_id=record.project_id,
                )
                bundle["qa_job"] = _job_payload(job)
            else:
                raise VideoFlowError(f"invalid qa_mode: {qa_mode}")
        return bundle

    @register
    def vf_export(
        action: str = "bundle",
        project_id: str = "",
        job_id: str = "",
        targets: str | list[str] | None = None,
        look: dict[str, Any] | None = None,
        audio_source: str = "mix",
        captions: bool = True,
        draft: bool = False,
        release_kit: bool = False,
        fps: int | str = 30,
        qa_mode: str = "fast",
        preset: str = "veryfast",
        kind: str = "timeline",
        crf: int = 20,
        width: int = 0,
        height: int = 0,
        draft_scale: float = 1.0,
        wait: bool = False,
        timeout_sec: float = 1800.0,
        direction: str = "pull",
        nle: str = "fcpxml",
        path: str = "",
        apply: bool = False,
        dialect: str = "1.10",
        mp4_profile: str = "youtube_h264",
        mp4_loudness_lufs: float | None = -16.5,
        burn_subtitles: bool | None = None,
    ) -> dict[str, Any]:
        """Render a bundle, start a draft render, validate exports, or run an NLE roundtrip."""

        if burn_subtitles is not None:
            captions = burn_subtitles
        if action == "render":
            response = legacy["vf_render_start"](
                project_id=project_id,
                kind=kind,
                crf=crf,
                preset=preset,
                width=width,
                height=height,
                draft_scale=draft_scale,
            )
            if wait and response.get("ok"):
                new_job_id = str((response.get("job") or {}).get("job_id") or "")
                if new_job_id:
                    response["wait"] = _wait(manager, project_id, new_job_id, timeout_sec)
            return response
        if action == "validate":
            return legacy["vf_validate_exports"](project_id=project_id, job_id=job_id)
        if action == "roundtrip":
            return legacy["vf_nle_roundtrip"](
                project_id=project_id,
                direction=direction,
                nle=nle,
                path=path,
                apply=apply,
            )
        if action != "bundle":
            return error(
                "unknown_action",
                "vf_export supports bundle, render, validate, or roundtrip",
            )
        if audio_source not in {"mix", "master", "timeline"}:
            return error("invalid_audio_source", "audio_source must be mix, master, or timeline")
        if qa_mode not in {"fast", "full", "off"}:
            return error("invalid_qa_mode", "qa_mode must be fast, full, or off")
        try:
            bundle = _run_bundle(
                project_id,
                targets=targets,
                look=look,
                audio_source=audio_source,
                captions=captions,
                draft=draft,
                dialect=dialect,
                mp4_profile=mp4_profile,
                mp4_loudness_lufs=mp4_loudness_lufs,
                fps=fps,
                qa_mode=qa_mode,
                mp4_preset=preset,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        response = {
            "ok": bool(bundle.get("ok")),
            "project_id": project_id,
            "targets": list(bundle.get("targets") or []),
            "bundle": bundle,
        }
        if release_kit:
            from videoflow.application.release_kit import build_release_kit

            try:
                response["release_kit"] = build_release_kit(project_id)
            except (VideoFlowError, OSError) as exc:
                response["release_kit_error"] = str(exc)
        return response

    @register
    def vf_interaction(
        action: str = "list",
        project_id: str = "",
        job_id: str = "",
        interaction_id: str = "",
        response_action: str = "submit",
        answers: dict[str, Any] | None = None,
        comment: str = "",
        pending_only: bool = True,
        channel: str = "local",
        token: str = "",
    ) -> dict[str, Any]:
        """List, read, or answer human-in-the-loop requests."""

        if action == "respond":
            return legacy["vf_respond_interaction"](
                project_id=project_id,
                interaction_id=interaction_id,
                action=response_action,
                answers=answers,
                comment=comment,
                job_id=job_id,
                channel=channel,
                token=token,
            )
        if job_id:
            try:
                jobs = [manager.get(job_id)]
            except VideoFlowError as exc:
                return exc.to_dict()
        else:
            jobs = manager.list()
        items: list[dict[str, Any]] = []
        for job in jobs:
            try:
                requests = list_requests(Path(job.output), job_id=str(job.job_id))
            except OSError:
                continue
            for request in requests:
                if pending_only and request.status != "pending":
                    continue
                payload = {
                    "job_id": str(job.job_id),
                    "interaction": public_payload(
                        Path(job.output),
                        request,
                        load_response(Path(job.output), request.interaction_id),
                    ),
                }
                if action == "get" and interaction_id and request.interaction_id != interaction_id:
                    continue
                items.append(payload)
        if action == "get" and interaction_id:
            return {"ok": bool(items), "interaction": items[0] if items else None}
        return {"ok": True, "interactions": items, "count": len(items)}

    @register
    def vf_ingest(
        action: str = "session",
        project_id: str = "",
        sources: list[str] | None = None,
        raw_dir: str = "",
        order: str = "auto",
        target_fps: float = 0.0,
        target_width: int = 0,
        target_height: int = 0,
        normalize: bool = False,
        primary_source_id: str = "",
        secondary_source_id: str = "",
        apply: bool = False,
        min_confidence: float = 0.2,
        compose: str = "none",
        pip_position: str = "top_right",
        pip_width_ratio: float = 0.28,
        wait: bool = False,
        timeout_sec: float = 1800.0,
    ) -> dict[str, Any]:
        """Run session ingest, multicam synchronization, or audio diagnosis."""

        if action == "diagnose":
            from videoflow.application.audio_diagnosis import diagnose_audio

            try:
                record = get_project(project_id)
                state = load_project_state(record)
                media = state.media_info
                source = Path(
                    media.source_path if media is not None else record.primary_source
                )
                if not source.is_file():
                    return error("source_not_found", f"Source is missing: {source}")
                return {
                    "ok": True,
                    "project_id": project_id,
                    "audio_diagnosis": diagnose_audio(source, media),
                }
            except VideoFlowError as exc:
                return exc.to_dict()
        mode = "multicam" if action == "multicam" else "session"
        step_type = "sync.multicam_audio" if mode == "multicam" else "session.ingest"
        if mode == "multicam":
            response = legacy["vf_sync_multicam"](
                project_id=project_id,
                primary_source_id=primary_source_id,
                secondary_source_id=secondary_source_id,
                apply=apply,
                min_confidence=min_confidence,
                compose=compose,
                pip_position=pip_position,
                pip_width_ratio=pip_width_ratio,
            )
        else:
            response = legacy["vf_ingest_session"](
                project_id=project_id,
                sources=sources,
                raw_dir=raw_dir,
                order=order,
                target_fps=target_fps,
                target_width=target_width,
                target_height=target_height,
                normalize=normalize,
            )
            if wait and response.get("ok"):
                job_id = str((response.get("job") or {}).get("job_id") or "")
                if job_id:
                    response["wait"] = _wait(manager, project_id, job_id, timeout_sec)
        if not response.get("ok"):
            return response
        response["mode"] = mode
        response["step_type"] = step_type
        try:
            state = load_project_state(get_project(project_id))
            media = state.media_info
            if media is not None and media.fps_num:
                response["source_duration_sec"] = round(
                    media.duration_frames / (media.fps_num / media.fps_den), 6
                )
                response["cfr_fps"] = round(media.fps_num / media.fps_den, 6)
            else:
                response["source_duration_sec"] = 0.0
                response["cfr_fps"] = 0.0
            response["pcm_path"] = state.pipeline.pcm_path
            offset_samples = state.source_offsets.get(state.primary_source_id, 0)
            rate = media.audio_sample_rate if media is not None else 48000
            response["audio_offset_ms"] = round(offset_samples / max(1, rate) * 1000, 3)
            if media is not None:
                from videoflow.application.audio_diagnosis import diagnose_audio

                try:
                    response["audio_diagnosis"] = diagnose_audio(
                        media.source_path, media
                    )
                except Exception as exc:  # noqa: BLE001 - diagnosis is advisory
                    response["audio_diagnosis"] = {
                        "ok": False,
                        "error": str(exc),
                    }
        except VideoFlowError:
            response.setdefault("source_duration_sec", 0.0)
            response.setdefault("cfr_fps", 0.0)
            response.setdefault("pcm_path", "")
            response.setdefault("audio_offset_ms", 0.0)
        return response

    register_scene_tools(register, ctx, wait_fn=_wait)
    register_format_tools(register)
