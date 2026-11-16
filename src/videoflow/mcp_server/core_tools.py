"""Consolidated 12-tool core MCP surface for VideoFlow 2.90."""

from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from vf_contracts.assets import iter_assets

from videoflow.application import artifacts as artifact_service
from videoflow.application.hilt import list_requests, load_response, public_payload
from videoflow.application.projects import get_project, load_project_state
from videoflow.domain.errors import VideoFlowError
from videoflow.engine.recipes import list_recipes
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
            return {"ok": False, "code": "timeout", "job": job.to_dict()}
        time.sleep(0.25)
        job = manager.get(job_id)
    return {"ok": job.status == "succeeded", "job": job.to_dict()}


def register_core_tools(register: Any, ctx: Any) -> None:
    legacy = _capture_legacy(register, ctx)
    manager = ctx.manager

    @register
    def vf_project(
        action: str = "status",
        project_id: str = "",
        name: str = "",
        output: str = "",
        sources: list[str] | None = None,
        channel_id: str = "",
    ) -> dict[str, Any]:
        """Create/open/status a project."""

        if action in {"init", "open"}:
            return legacy["vf_project_init"](
                project_id=project_id,
                name=name,
                output=output,
                sources=sources,
                channel_id=channel_id,
            )
        if not project_id:
            return error("project_required", "project_id is required")
        return legacy["vf_project_status"](project_id=project_id)

    @register
    def vf_capabilities(allow_external_services: bool = False) -> dict[str, Any]:
        """Backends, models, and external-provider policy."""

        return legacy["vf_capabilities"](allow_external_services=allow_external_services)

    @register
    def vf_catalog_search(query: str = "", kind: str = "all", limit: int = 20) -> dict[str, Any]:
        """Search steps and recipes without loading their schemas."""

        needle = query.strip().casefold()
        cap = max(1, min(100, int(limit)))
        result: dict[str, Any] = {"ok": True, "query": query, "steps": [], "recipes": []}
        if kind in {"all", "steps"}:
            for step in _step_catalog():
                haystack = (f"{step['type']} {step['title']} {step['description']}").casefold()
                if needle and needle not in haystack:
                    continue
                result["steps"].append(step)
                if len(result["steps"]) >= cap:
                    break
        if kind in {"all", "recipes"}:
            for recipe in list_recipes():
                haystack = f"{recipe.get('id', '')} {recipe.get('name', '')}".casefold()
                if needle and needle not in haystack:
                    continue
                result["recipes"].append(recipe)
                if len(result["recipes"]) >= cap:
                    break
        return result

    @register
    def vf_exec(
        action: str = "recipe",
        project_id: str = "",
        recipe_id: str = "",
        recipe: dict[str, Any] | None = None,
        step_id: str = "",
        params: dict[str, Any] | None = None,
        source: str = "",
        variables: dict[str, Any] | None = None,
        profile: str = "",
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
        """Run a recipe/step, or edit one Short in a project."""

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
            response = {"ok": True, "job": job.to_dict(), "project_id": project_id}
        else:
            response = legacy["vf_run_recipe"](
                project_id=project_id,
                recipe_id=recipe_id,
                recipe=recipe,
                source=source,
                variables=variables,
                profile=profile,
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
    ) -> dict[str, Any]:
        """Read or edit the canonical timeline."""

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
    ) -> dict[str, Any]:
        """Validate exports or run an NLE roundtrip."""

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
