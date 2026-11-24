"""VideoFlow core MCP tools: projects, capabilities and interaction."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from videoflow.application.brand_kit import brand_kit_ids, is_brand_kit
from videoflow.application.hilt import list_requests, load_response, public_payload
from videoflow.application.projects import (
    get_project,
    list_projects,
    project_output_dir,
    project_uuid,
)
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.context import error, unknown_action

from .core_shared import (
    _step_catalog,
)

PROJECT_ACTIONS = (
    "status",
    "session_brief",
    "checkpoint",
    "checkpoints",
    "restore_checkpoint",
    "list",
    "archive",
    "unarchive",
    "delete",
    "history",
    "undo",
    "restore",
    "clone",
    "clone_style",
    "learn_rule",
    "init",
    "create",
    "new",
    "open",
)


def register(register: Any, ctx: Any, legacy: dict[str, Any]) -> None:
    manager = ctx.manager

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

        if action not in PROJECT_ACTIONS:
            return unknown_action("vf_project", action, PROJECT_ACTIONS)
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
        if action in {"init", "create", "new", "open"}:
            if not project_id and not name and not output:
                return error(
                    "project_required",
                    "Pass project_id or name when creating a project",
                )
            if not project_id and name:
                project_id = _project_slug(name)
            if not output:
                try:
                    output = str(project_output_dir(project_id))
                except ValueError as exc:
                    return error("invalid_project_id", str(exc))
            if channel_id and not is_brand_kit(channel_id):
                return error(
                    "channel_not_found",
                    f"Unknown channel kit: {channel_id}. Use one of: "
                    + ", ".join(brand_kit_ids())
                    + ". Styles belong in style_id.",
                )
            if style_id:
                from videoflow.application.style_catalog import StyleCatalog

                try:
                    StyleCatalog().get(style_id)
                except VideoFlowError as exc:
                    return exc.to_dict()
            result = legacy["vf_project_init"](
                project_id=project_id,
                name=name,
                output=output,
                sources=sources,
                channel_id=channel_id,
                style_id=style_id,
            )
            if isinstance(result, dict) and result.get("ok"):
                project = result.get("project") or {}
                result["project_id"] = project.get("project_id", project_id)
                result["uuid"] = str(project_uuid(result["project_id"]))
            return result
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


def _project_slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "").strip()).strip("-")
    return (text or "project")[:128]
