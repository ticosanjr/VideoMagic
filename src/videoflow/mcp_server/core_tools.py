"""Consolidated 13-tool core MCP surface for VideoFlow 2.91."""

from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from vf_contracts.assets import iter_assets

from videoflow.application import artifacts as artifact_service
from videoflow.application.channel_kit import channel_kit_ids, is_channel_kit
from videoflow.application.hilt import list_requests, load_response, public_payload
from videoflow.application.projects import get_project, load_project_state
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.agent_helpers import _job_payload
from videoflow.mcp_server.agent_tools import register_agent_tools
from videoflow.mcp_server.context import error
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


def _wait(manager: Any, project_id: str, job_id: str, timeout: float) -> dict[str, Any]:
    record = get_project(project_id)
    job = manager.get(job_id)
    if getattr(job, "project_id", "") not in {"", record.project_id}:
        return error("job_mismatch", "Job does not belong to this project")
    deadline = time.monotonic() + max(1.0, min(3600.0, timeout))
    while job.status not in {"succeeded", "failed", "cancelled", "answered"}:
        if time.monotonic() >= deadline:
            return {"ok": False, "code": "timeout", "job": _job_payload(job)}
        time.sleep(0.25)
        job = manager.get(job_id)
    return {"ok": job.status == "succeeded", "job": _job_payload(job)}


def register_core_tools(register: Any, ctx: Any) -> None:
    legacy = _capture_legacy(register, ctx)
    manager = ctx.manager

    @register
    def vf_style(
        action: str = "list",
        style_id: str = "",
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
        """List, save, sync, or learn rules for the Markdown style catalog."""

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
            if action != "save":
                return error("unknown_action", f"Unknown style action: {action}")
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
    def vf_style_list(workspace_dir: str = "") -> dict[str, Any]:
        """List the Markdown style catalog."""

        return vf_style(action="list", workspace_dir=workspace_dir)

    @register
    def vf_style_save(
        style_id: str = "",
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
        workspace_dir: str = "",
        overwrite: bool = True,
    ) -> dict[str, Any]:
        """Create or update one Markdown style and sync presets/."""

        return vf_style(
            action="save",
            style_id=style_id,
            name=name,
            markdown_content=markdown_content,
            body=body,
            aspect_ratio=aspect_ratio,
            target_lufs=target_lufs,
            max_static_sec=max_static_sec,
            min_silence_ms=min_silence_ms,
            layout_mode=layout_mode,
            caption_preset=caption_preset,
            motion_engine=motion_engine,
            platforms=platforms,
            beatmap_defaults=beatmap_defaults,
            sound_design=sound_design,
            hook_strategy=hook_strategy,
            intro_strategy=intro_strategy,
            export_targets=export_targets,
            palette=palette,
            fonts=fonts,
            cut_rhythm=cut_rhythm,
            safe_zones=safe_zones,
            workspace_dir=workspace_dir,
            overwrite=overwrite,
        )

    @register
    def vf_style_learn_rule(
        style_id: str,
        feedback_note: str = "",
        notes: list[str] | None = None,
        mode: str = "merge",
        max_rules: int = 15,
        workspace_dir: str = "",
    ) -> dict[str, Any]:
        """Append review notes to one style, capped at 15 consolidated rules."""

        return vf_style(
            action="learn_rule",
            style_id=style_id,
            feedback_note=feedback_note,
            notes=notes,
            mode=mode,
            max_rules=max_rules,
            workspace_dir=workspace_dir,
        )

    @register
    def analyze_reference_style(
        style_id: str = "",
        name: str = "",
        reference_url: str = "",
        reference_dir: str = "",
        images: list[str] | None = None,
        workspace_dir: str = "",
    ) -> dict[str, Any]:
        """Analyze a URL, folder, or images and return a style candidate without saving."""

        return vf_style(
            action="analyze",
            style_id=style_id,
            name=name,
            reference_url=reference_url,
            reference_dir=reference_dir,
            images=images,
            workspace_dir=workspace_dir,
        )

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
    ) -> dict[str, Any]:
        """Create/open/status a project, clone a style, or learn channel rules."""

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

        return legacy["vf_capabilities"](allow_external_services=allow_external_services)

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
    def vf_job(
        action: str = "get",
        project_id: str = "",
        job_id: str = "",
        step_id: str = "",
        tail_lines: int = 100,
        timeout_sec: float = 300.0,
    ) -> dict[str, Any]:
        """Get, wait, inspect logs, or read QA for a job."""

        if action == "logs":
            return legacy["vf_get_step_logs"](
                project_id=project_id,
                job_id=job_id,
                step_id=step_id,
                tail_lines=tail_lines,
            )
        if action == "qa":
            return legacy["vf_get_qa_artifacts"](project_id=project_id, include_images=False)[0]
        if action == "wait":
            try:
                return _wait(manager, project_id, job_id, timeout_sec)
            except VideoFlowError as exc:
                return exc.to_dict()
        return legacy["vf_get_job"](project_id=project_id, job_id=job_id)

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
    ) -> dict[str, Any]:
        """Read, edit, or atomically apply a declarative beatmap."""

        if action == "apply_beatmap":
            from videoflow.application.beatmap import (
                BeatmapError,
                apply_beatmap,
                write_beatmap_sidecar,
            )
            from videoflow.application.projects import save_project_state

            if not beatmap:
                return error("beatmap_required", "Pass a beatmap manifest")
            try:
                record = get_project(project_id)
                state = load_project_state(record)
                updated, report, sidecar = apply_beatmap(
                    state,
                    Path(record.output),
                    beatmap,
                    expected_revision=expected_revision,
                )
                saved = save_project_state(
                    record,
                    updated,
                    expected_revision=expected_revision,
                    bump_revision=True,
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
            except VideoFlowError as exc:
                return exc.to_dict()
        if action == "edit":
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

    @register
    def vf_render(
        action: str = "start",
        project_id: str = "",
        job_id: str = "",
        kind: str = "timeline",
        crf: int = 20,
        preset: str = "veryfast",
        width: int = 0,
        height: int = 0,
        draft_scale: float = 1.0,
    ) -> dict[str, Any]:
        """Start, inspect, or cancel a render job."""

        if action == "start":
            return legacy["vf_render_start"](
                project_id=project_id,
                kind=kind,
                crf=crf,
                preset=preset,
                width=width,
                height=height,
                draft_scale=draft_scale,
            )
        if action == "cancel":
            try:
                manager.cancel(job_id)
            except VideoFlowError as exc:
                return exc.to_dict()
            return {"ok": True, "job_id": job_id}
        return legacy["vf_get_job"](project_id=project_id, job_id=job_id)

    @register
    def vf_exports(
        action: str = "validate",
        project_id: str = "",
        job_id: str = "",
        direction: str = "pull",
        nle: str = "fcpxml",
        path: str = "",
        apply: bool = False,
        targets: str | list[str] | None = None,
        dialect: str = "1.10",
        mp4_profile: str = "youtube_h264",
        mp4_loudness_lufs: float | None = -16.5,
        burn_subtitles: bool = True,
    ) -> dict[str, Any]:
        """Export a multi-target bundle, validate it, or run an NLE roundtrip."""

        if action == "bundle":
            from videoflow.application.delivery_bundle import (
                DEFAULT_BUNDLE_TARGETS,
                DeliveryBundleRequest,
                build_delivery_bundle,
            )

            requested = [targets] if isinstance(targets, str) else targets
            try:
                record = get_project(project_id)
                state = load_project_state(record)
                if not state.video_segments:
                    return error("timeline_required", "Project has no built timeline")
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
                bundle = build_delivery_bundle(
                    state,
                    Path(record.output),
                    request=DeliveryBundleRequest(
                        targets=tuple(requested),
                        dialect=dialect,  # type: ignore[arg-type]
                        mp4_profile=mp4_profile,
                        mp4_loudness_lufs=mp4_loudness_lufs,
                        burn_subtitles=burn_subtitles,
                    ),
                )
                return {"ok": bool(bundle.get("ok")), "bundle": bundle}
            except VideoFlowError as exc:
                return exc.to_dict()
        if action == "roundtrip":
            return legacy["vf_nle_roundtrip"](
                project_id=project_id,
                direction=direction,
                nle=nle,
                path=path,
                apply=apply,
            )
        return legacy["vf_validate_exports"](project_id=project_id, job_id=job_id)

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
        jobs = [manager.get(job_id)] if job_id else manager.list()
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
    ) -> dict[str, Any]:
        """Run session ingest or multicam synchronization."""

        if action == "multicam":
            return legacy["vf_sync_multicam"](
                project_id=project_id,
                primary_source_id=primary_source_id,
                secondary_source_id=secondary_source_id,
                apply=apply,
                min_confidence=min_confidence,
                compose=compose,
                pip_position=pip_position,
                pip_width_ratio=pip_width_ratio,
            )
        return legacy["vf_ingest_session"](
            project_id=project_id,
            sources=sources,
            raw_dir=raw_dir,
            order=order,
            target_fps=target_fps,
            target_width=target_width,
            target_height=target_height,
            normalize=normalize,
        )

    @register
    def vf_qa(
        action: str = "artifacts",
        project_id: str = "",
        include_images: bool = False,
    ) -> Any:
        """Read QA artifacts or run project QA later through vf_exec."""

        if action == "artifacts":
            return legacy["vf_get_qa_artifacts"](
                project_id=project_id, include_images=include_images
            )
        try:
            state = load_project_state(get_project(project_id))
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "action": action,
            "revision": state.revision,
            "message": "Use vf_exec with qa.visual_10fps or qa.safezone for new QA runs.",
        }
