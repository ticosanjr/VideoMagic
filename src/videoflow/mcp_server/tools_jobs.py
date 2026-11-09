"""MCP job, HILT, and recipe execution tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.application import hilt, recipe_meta
from videoflow.application.deliverables import approve_review
from videoflow.application.nle_validation import validate_nle_exports
from videoflow.core.recipe import parse_recipe, recipe_to_dict
from videoflow.domain.errors import RecipeError, StateNotReadyError, VideoFlowError
from videoflow.domain.paths import resolve_allowed
from videoflow.engine.recipes import (
    get_recipe,
    list_recipes,
    resolve_recipe_paths,
    save_user_recipe,
)
from videoflow.mcp_server.context import ToolContext, error, source_required
from videoflow.runtime import allowed_roots
from videoflow.steps import get_step, requirements_by_type, step_types
from videoflow.steps import manifest as step_manifest
from videoflow.steps.ports import validate_recipe_ports


def register_job_tools(register: Any, ctx: ToolContext) -> None:
    """Register job lifecycle, HILT, and recipe tools."""

    manager = ctx.manager
    batch_manager = ctx.batch_manager
    last = ctx.last

    @register
    def videoflow_get_job(job_id: str) -> dict[str, object]:
        """Return the status and report of one job."""

        try:
            job = manager.get(job_id)
        except VideoFlowError as exc:
            return exc.to_dict()
        if str(job.job_id) == last.get("job_id"):
            last["output"] = job.output
        return {"ok": True, "job": job.to_dict()}

    @register
    def videoflow_list_interactions(
        job_id: str = "", pending_only: bool = True
    ) -> dict[str, object]:
        """List human-in-the-loop requests, optionally for one job."""

        items: list[dict[str, object]] = []
        jobs = [manager.get(job_id)] if job_id else manager.list()
        for job in jobs:
            if job_id and job.status not in {"waiting_approval", "waiting_input"}:
                continue
            try:
                requests = hilt.list_requests(job.output, job_id=str(job.job_id))
            except OSError:
                continue
            for request in requests:
                if pending_only and request.status != "pending":
                    continue
                response = hilt.load_response(job.output, request.interaction_id)
                items.append(
                    {
                        "job_id": str(job.job_id),
                        "job_status": job.status,
                        "interaction": hilt.public_payload(
                            job.output, request, response
                        ),
                    }
                )
        return {"ok": True, "interactions": items, "count": len(items)}

    @register
    def videoflow_get_interaction(
        job_id: str, interaction_id: str
    ) -> dict[str, object]:
        """Return one HILT request, its response, and review artifacts."""

        try:
            job = manager.get(job_id)
            request = hilt.find_request(job.output, job_id, interaction_id)
            response = hilt.load_response(job.output, interaction_id)
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "interaction": hilt.public_payload(job.output, request, response),
        }

    @register
    def videoflow_respond_to_interaction(
        job_id: str,
        interaction_id: str,
        action: str = "submit",
        answers: dict[str, Any] | None = None,
        comment: str = "",
        channel: str = "local",
        token: str = "",
    ) -> dict[str, object]:
        """Answer a waiting HILT request and resume the recipe."""

        try:
            job = manager.get(job_id)
            if job.status not in {"waiting_approval", "waiting_input"}:
                raise StateNotReadyError(
                    "The job is not waiting for a human response."
                )
            existing = hilt.load_response(job.output, interaction_id)
            if existing is not None and existing.resumed_job_id:
                resumed = manager.get(existing.resumed_job_id)
                return {"ok": True, "job": resumed.to_dict(), "duplicate": True}
            _request, response = hilt.respond(
                job.output,
                job_id,
                interaction_id,
                action=action,
                answers=answers or {},
                comment=comment,
                channel=channel,
                token=token,
            )
            resumed = manager.start(
                job.source,
                job.output,
                {**job.options, "resume": True},
                queue=True,
            )
            hilt.mark_resumed(job.output, interaction_id, str(resumed.job_id))
            manager.mark_answered(job_id, str(resumed.job_id))
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "job": resumed.to_dict(),
            "action": response.action,
        }

    @register
    def videoflow_cancel_job(job_id: str) -> dict[str, object]:
        """Ask the active job to stop between stages."""

        try:
            return {"ok": True, "job": manager.cancel(job_id).to_dict()}
        except VideoFlowError as exc:
            return exc.to_dict()

    @register
    def videoflow_decide_review(
        approved: bool,
        comment: str = "",
        reviewer: str = "",
        job_id: str | None = None,
    ) -> dict[str, object]:
        """Approve or reject the review checklist for a job."""

        try:
            job = ctx.timeline_job(job_id)
            approval = approve_review(
                job.output,
                approved=approved,
                comment=comment,
                reviewer=reviewer,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "approval": approval}

    @register
    def videoflow_list_jobs(
        limit: int = 20, offset: int = 0, summary: bool = True
    ) -> dict[str, object]:
        """List jobs newest first with status, progress, and attempts."""

        all_jobs = manager.list(limit=None, offset=0)
        start = max(0, offset)
        page = all_jobs[start : start + max(1, min(limit, 1000))]
        return {
            "ok": True,
            "jobs": [job.to_dict(summary=summary) for job in page],
            "total": len(all_jobs),
        }

    @register
    def videoflow_pause_job(job_id: str) -> dict[str, object]:
        """Pause a queued job or request a cooperative pause for a running one."""

        try:
            return {"ok": True, "job": manager.pause(job_id).to_dict()}
        except VideoFlowError as exc:
            return exc.to_dict()

    @register
    def videoflow_unpause_job(job_id: str) -> dict[str, object]:
        """Requeue a paused job."""

        try:
            return {"ok": True, "job": manager.unpause(job_id).to_dict()}
        except VideoFlowError as exc:
            return exc.to_dict()

    @register
    def videoflow_set_job_priority(job_id: str, priority: int) -> dict[str, object]:
        """Set a job priority and reorder the pending queue."""

        try:
            return {
                "ok": True,
                "job": manager.set_priority(job_id, priority).to_dict(),
            }
        except VideoFlowError as exc:
            return exc.to_dict()

    @register
    def videoflow_validate_exports(job_id: str | None = None) -> dict[str, object]:
        """Validate the FCPXML, XMEML, and Kdenlive exports of a job."""

        try:
            job = ctx.timeline_job(job_id)
        except VideoFlowError as exc:
            return exc.to_dict()
        return validate_nle_exports(job.output / "exports")

    @register
    def videoflow_list_steps(
        limit: int = 200, offset: int = 0
    ) -> dict[str, object]:
        """List every recipe step and its JSON parameter schema."""

        items = step_manifest()
        start = max(0, offset)
        page = items[start : start + max(1, min(limit, 1000))]
        return {"ok": True, "steps": page, "total": len(items)}

    @register
    def videoflow_list_recipes(
        limit: int = 200, offset: int = 0
    ) -> dict[str, object]:
        """List built-in and operator recipes."""

        items = recipe_meta.decorate(list_recipes())
        start = max(0, offset)
        page = items[start : start + max(1, min(limit, 1000))]
        return {"ok": True, "recipes": page, "total": len(items)}

    @register
    def videoflow_get_recipe(recipe_id: str) -> dict[str, object]:
        """Return one complete recipe document."""

        try:
            recipe = get_recipe(recipe_id)
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "recipe": recipe_to_dict(recipe)}

    @register
    def videoflow_validate_recipe(
        recipe: dict[str, object], through: str | None = None
    ) -> dict[str, object]:
        """Validate a recipe DAG and return its execution order."""

        try:
            parsed = parse_recipe(recipe)  # type: ignore[arg-type]
            parsed.validate_graph(step_types(), requires_by_type=requirements_by_type())
            validate_recipe_ports(parsed, through=through)
            resolved = parsed.with_variables({})
            allowed = parsed.ids_through(through) if through is not None else None
            for step in resolved.steps:
                if allowed is not None and step.id not in allowed:
                    continue
                try:
                    get_step(step.type).validate_params(step.params)
                except ValueError as exc:
                    errors = exc.errors() if hasattr(exc, "errors") else []
                    detail = (
                        errors[0].get("msg", "invalid parameters")
                        if errors
                        else str(exc)
                    )
                    raise RecipeError(f"{step.id}: {detail}") from exc
            order = [step.id for step in parsed.topological_order()]
        except VideoFlowError as exc:
            return exc.to_dict()
        except ValueError as exc:
            return error("recipe_invalid", str(exc))
        return {
            "ok": True,
            "recipe": recipe_to_dict(parsed),
            "resolved": recipe_to_dict(resolved),
            "order": order,
        }

    @register
    def videoflow_save_recipe(recipe: dict[str, object]) -> dict[str, object]:
        """Validate and save a recipe under the VideoFlow home directory."""

        try:
            parsed = parse_recipe(recipe)  # type: ignore[arg-type]
            parsed.validate_graph(step_types(), requires_by_type=requirements_by_type())
            validate_recipe_ports(parsed)
            path = save_user_recipe(parsed)
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "recipe": recipe_to_dict(parsed), "path": str(path)}

    @register
    def videoflow_run_recipe(
        recipe_id: str,
        source: str | None = None,
        output: str | None = None,
        resume: bool = True,
    ) -> dict[str, object]:
        """Run a named recipe on a source file and return the job."""

        try:
            source_path = Path(source) if source else last.get("source")
            if not isinstance(source_path, Path):
                return source_required()
            roots = allowed_roots()
            resolved_source = resolve_allowed(source_path, roots)
            output_path = (
                Path(output)
                if output
                else resolved_source.with_name(f"{resolved_source.stem}-videoflow")
            )
            resolved_output = resolve_allowed(output_path, roots)
            recipe = get_recipe(recipe_id)
            recipe = resolve_recipe_paths(recipe, roots)
            recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
            validate_recipe_ports(recipe)
            job = manager.start(
                resolved_source,
                resolved_output,
                {
                    "mode": "recipe",
                    "recipe": recipe.model_dump(mode="json"),
                    "resume": resume,
                },
                queue=True,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        recipe_meta.touch(recipe.id)
        last["source"] = resolved_source
        last["output"] = resolved_output
        last["job_id"] = str(job.job_id)
        return {"ok": True, "job": job.to_dict()}

    @register
    def videoflow_run_recipe_inline(
        recipe: dict[str, object],
        source: str | None = None,
        output: str | None = None,
        resume: bool = True,
    ) -> dict[str, object]:
        """Run an inline recipe on a source file and return the job."""

        try:
            source_path = Path(source) if source else last.get("source")
            if not isinstance(source_path, Path):
                return source_required()
            roots = allowed_roots()
            resolved_source = resolve_allowed(source_path, roots)
            output_path = (
                Path(output)
                if output
                else resolved_source.with_name(f"{resolved_source.stem}-videoflow")
            )
            resolved_output = resolve_allowed(output_path, roots)
            parsed = parse_recipe(recipe)  # type: ignore[arg-type]
            parsed = resolve_recipe_paths(parsed, roots)
            parsed.validate_graph(step_types(), requires_by_type=requirements_by_type())
            validate_recipe_ports(parsed)
            job = manager.start(
                resolved_source,
                resolved_output,
                {
                    "mode": "recipe",
                    "recipe": parsed.model_dump(mode="json"),
                    "resume": resume,
                },
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        recipe_meta.touch(parsed.id)
        last["source"] = resolved_source
        last["output"] = resolved_output
        last["job_id"] = str(job.job_id)
        return {"ok": True, "job": job.to_dict()}

    @register
    def videoflow_run_step(
        step_id: str,
        recipe: dict[str, object] | None = None,
        recipe_id: str | None = None,
        source: str | None = None,
        output: str | None = None,
        resume: bool = True,
    ) -> dict[str, object]:
        """Run the dependencies and one named step, then stop."""

        try:
            if (recipe is None) == (recipe_id is None):
                return error(
                    "recipe_required", "Provide exactly one of recipe or recipe_id."
                )
            parsed = (
                parse_recipe(recipe)  # type: ignore[arg-type]
                if recipe is not None
                else get_recipe(str(recipe_id))
            )
            source_path = Path(source) if source else last.get("source")
            if not isinstance(source_path, Path):
                return source_required()
            roots = allowed_roots()
            resolved_source = resolve_allowed(source_path, roots)
            output_path = (
                Path(output)
                if output
                else resolved_source.with_name(f"{resolved_source.stem}-videoflow")
            )
            resolved_output = resolve_allowed(output_path, roots)
            parsed = resolve_recipe_paths(parsed, roots)
            parsed.validate_graph(step_types(), requires_by_type=requirements_by_type())
            if step_id not in {step.id for step in parsed.enabled_steps()}:
                return error("unknown_step", f"Unknown or disabled step: {step_id}")
            validate_recipe_ports(parsed, through=step_id)
            job = manager.start(
                resolved_source,
                resolved_output,
                {
                    "mode": "recipe",
                    "recipe": parsed.model_dump(mode="json"),
                    "through": step_id,
                    "resume": resume,
                },
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        last["source"] = resolved_source
        last["output"] = resolved_output
        last["job_id"] = str(job.job_id)
        return {"ok": True, "job": job.to_dict()}

    @register
    def videoflow_run_batch(
        recipe: dict[str, object] | None = None,
        recipe_id: str | None = None,
        source_dir: str = "",
        output_root: str = "",
        recursive: bool = False,
        extensions: list[str] | None = None,
        resume: bool = True,
    ) -> dict[str, object]:
        """Run a recipe over every matching media file in a folder."""

        try:
            if (recipe is None) == (recipe_id is None):
                return error(
                    "recipe_required", "Provide exactly one of recipe or recipe_id."
                )
            parsed = (
                parse_recipe(recipe)  # type: ignore[arg-type]
                if recipe is not None
                else get_recipe(str(recipe_id))
            )
            roots = allowed_roots()
            resolved_source = resolve_allowed(Path(source_dir), roots)
            resolved_output = resolve_allowed(Path(output_root), roots)
            parsed = resolve_recipe_paths(parsed, roots)
            parsed.validate_graph(step_types(), requires_by_type=requirements_by_type())
            validate_recipe_ports(parsed)
            batch = batch_manager.start(
                resolved_source,
                resolved_output,
                parsed.model_dump(mode="json"),
                recipe_id=parsed.id,
                recursive=recursive,
                extensions=list(extensions or []),
                resume=resume,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "batch": batch.to_dict()}

    @register
    def videoflow_get_batch(batch_id: str) -> dict[str, object]:
        """Return one folder batch and its item statuses."""

        try:
            return {"ok": True, "batch": batch_manager.get(batch_id).to_dict()}
        except VideoFlowError as exc:
            return exc.to_dict()

    @register
    def videoflow_cancel_batch(batch_id: str) -> dict[str, object]:
        """Cancel a folder batch and its current job."""

        try:
            return {"ok": True, "batch": batch_manager.cancel(batch_id).to_dict()}
        except VideoFlowError as exc:
            return exc.to_dict()
