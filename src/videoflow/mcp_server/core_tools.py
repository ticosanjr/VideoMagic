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
from videoflow.application.projects import get_project, list_projects, load_project_state
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
    while job.status not in {"succeeded", "failed", "cancelled", "answered"}:
        if time.monotonic() >= deadline:
            return {"ok": False, "code": "timeout", "job": _job_payload(job)}
        time.sleep(0.5)
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
        revision_id: str = "",
        force: bool = False,
        status: str = "",
        include_archived: bool = False,
    ) -> dict[str, Any]:
        """Create/open/status a project, manage lifecycle, or undo revisions."""

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
                cloned, state = clone_project(get_project(project_id), name=name, output=output)
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
    def vf_jobs(
        action: str = "list",
        project_id: str = "",
        status: str = "",
        job_id: str = "",
        limit: int = 20,
        force: bool = False,
    ) -> dict[str, Any]:
        """List, inspect, or cancel jobs in the shared queue."""

        from videoflow.application import database

        cap = max(1, min(200, int(limit)))
        if action == "list":
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
        if not job_id:
            return error("job_required", "job_id is required")
        if action == "cancel":
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
        if action != "status":
            return error("unknown_action", "vf_jobs supports list, status, or cancel")
        try:
            return {"ok": True, "job": _job_payload(manager.get(job_id))}
        except VideoFlowError:
            stored = database.list_jobs(job_id=job_id, limit=1)
            if not stored:
                return error("job_not_found", f"Unknown job: {job_id}")
            return {"ok": True, "job": stored[0]}

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
        time_basis: str = "timeline",
        keep_ranges: list[dict[str, Any]] | None = None,
        remove_ranges: list[dict[str, Any]] | None = None,
        dry_run: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        """Read, edit, or atomically apply a declarative beatmap."""

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
        wait: bool = False,
        timeout_sec: float = 1800.0,
    ) -> dict[str, Any]:
        """Start, inspect, or cancel a render job."""

        if action == "start":
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
                job_id = str((response.get("job") or {}).get("job_id") or "")
                if job_id:
                    response["wait"] = _wait(manager, project_id, job_id, timeout_sec)
            return response
        if action == "cancel":
            try:
                manager.cancel(job_id)
            except VideoFlowError as exc:
                return exc.to_dict()
            return {"ok": True, "job_id": job_id}
        return legacy["vf_get_job"](project_id=project_id, job_id=job_id)

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
        return build_delivery_bundle(
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
            ),
        )

    @register
    def vf_export(
        project_id: str,
        targets: str | list[str] | None = None,
        look: dict[str, Any] | None = None,
        audio_source: str = "mix",
        captions: bool = True,
        draft: bool = False,
    ) -> dict[str, Any]:
        """Render the canonical master and every requested NLE target."""

        if audio_source not in {"mix", "master", "timeline"}:
            return error("invalid_audio_source", "audio_source must be mix, master, or timeline")
        try:
            bundle = _run_bundle(
                project_id,
                targets=targets,
                look=look,
                audio_source=audio_source,
                captions=captions,
                draft=draft,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": bool(bundle.get("ok")),
            "project_id": project_id,
            "targets": list(bundle.get("targets") or []),
            "bundle": bundle,
        }

    @register
    def vf_crop_preview(
        project_id: str,
        time_sec: float = 0.0,
        aspect: str = "9:16",
        fx: float = 0.5,
        fy: float = 0.5,
    ) -> dict[str, Any]:
        """Extract one frame with the crop rectangle and rule-of-thirds grid."""

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
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except ValueError as exc:
            return error("invalid_crop", str(exc))
        return {"ok": True, "project_id": project_id, "preview": result}

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
            try:
                bundle = _run_bundle(
                    project_id,
                    targets=targets,
                    audio_source="master",
                    captions=burn_subtitles,
                    dialect=dialect,
                    mp4_profile=mp4_profile,
                    mp4_loudness_lufs=mp4_loudness_lufs,
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
