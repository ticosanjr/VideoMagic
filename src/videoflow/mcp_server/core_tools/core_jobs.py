"""VideoFlow core MCP tools: jobs, runs and artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vf_shared.contracts.assets import iter_assets

from videoflow.application import artifacts as artifact_service
from videoflow.application.projects import get_project
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.agent_helpers import _job_payload
from videoflow.mcp_server.context import error, unknown_action

from .core_shared import (
    _is_step,
    _wait,
)


def _distribute_params(
    steps: list[str],
    params: dict[str, Any] | None,
    step_params: dict[str, dict[str, Any]] | None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if step_params:
        return (
            {
                str(step): dict(value)
                for step, value in step_params.items()
                if isinstance(value, dict)
            },
            [],
        )
    flat = dict(params or {})
    if not flat:
        return {}, []
    from videoflow.steps.registry import get_step

    distributed: dict[str, dict[str, Any]] = {}
    known: set[str] = set()
    for step in steps:
        try:
            fields = set(get_step(step).params_model.model_fields)
        except VideoFlowError:
            continue
        selected = {key: value for key, value in flat.items() if key in fields}
        if selected:
            distributed[step] = selected
            known.update(selected)
    return distributed, sorted(set(flat) - known)


def register(register: Any, ctx: Any, legacy: dict[str, Any]) -> None:
    manager = ctx.manager

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
            return unknown_action(
                "vf_exec",
                action,
                ("step", "short"),
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
        step_params: dict[str, dict[str, Any]] | None = None,
        resume: bool = True,
        wait: bool = True,
        timeout_sec: float = 600.0,
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
        distributed, invalid = _distribute_params(requested, params, step_params)
        if invalid:
            return error(
                "invalid_params",
                "Parameter(s) do not belong to any requested step: "
                + ", ".join(invalid),
                invalid_keys=invalid,
                steps=requested,
            )
        job = manager.start(
            Path(record.primary_source or record.output),
            Path(record.output),
            {
                "mode": "run",
                "project_id": record.project_id,
                "steps": requested,
                "through": through or "",
                "params": {},
                "step_params": distributed,
                "resume": bool(resume),
            },
            queue=True,
            project_id=record.project_id,
        )
        response: dict[str, Any] = {
            "ok": True,
            "project_id": project_id,
            "steps": requested,
            "step_params": distributed,
            "job": _job_payload(job),
        }
        if wait:
            waited = _wait(manager, project_id, str(job.job_id), timeout_sec)
            response["wait"] = waited
            if isinstance(waited.get("job"), dict):
                response["job"] = waited["job"]
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
                waited = _wait(manager, project_id, job_id, timeout_sec)
            except VideoFlowError as exc:
                return exc.to_dict()
            job = waited.get("job") if isinstance(waited, dict) else {}
            job = job if isinstance(job, dict) else {}
            live = None
            try:
                live = manager.get(job_id)
            except VideoFlowError:
                live = None
            live_result = getattr(live, "result", None)
            live_error = getattr(live, "error", None)
            payload = {
                "ok": bool(waited.get("ok")),
                "job_id": str(job.get("job_id") or job_id),
                "status": str(job.get("status") or getattr(live, "status", "")),
                "result": live_result if live_result is not None else job.get("result"),
                "error": live_error if live_error is not None else job.get("error"),
                "artifacts": job.get("artifacts") or [],
                "job": job,
            }
            if isinstance(payload["result"], dict):
                payload["artifacts"] = (
                    payload["result"].get("artifacts") or payload["artifacts"]
                )
            if waited.get("code"):
                payload["code"] = waited.get("code")
            return payload
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
        return unknown_action(
            "vf_job",
            action,
            ("list", "cancel", "get", "status", "wait", "logs", "qa"),
        )

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
                from vf_shared.contracts.workspace import project_dir

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
