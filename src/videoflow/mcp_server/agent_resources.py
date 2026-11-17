"""Project-scoped MCP resources for the agent profile."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from videoflow.application.artifacts import list_artifacts
from videoflow.application.preset_rules import load_rulebook
from videoflow.application.projects import (
    ProjectRecord,
    get_project,
    list_projects,
    load_project_state,
)
from videoflow.domain.errors import VideoFlowError
from videoflow.domain.transcript import format_srt
from videoflow.steps.registry import get_step


def _state(record: ProjectRecord):
    return load_project_state(record)


def _error(code: str, message: str) -> str:
    return json.dumps({"ok": False, "code": code, "message": message})


def register_agent_resources(mcp: Any, ctx: Any, *, prompts: bool = True) -> None:
    manager = ctx.manager

    if prompts:

        @mcp.prompt(
            name="videoflow_produce",
            description="Plan and run catalog steps end to end, then report artifacts.",
        )
        def produce_prompt(project_id: str, step_ids: str = "") -> str:
            return (
                f"Use vf_catalog_search (or vf://docs/steps) to choose the nodes for project "
                f"{project_id}. Run each node with vf_exec(action='step', step_id=..., "
                "params=...), poll with vf_job(action='wait'), then summarize artifacts and QA. "
                f"Suggested order: {step_ids or 'choose from the catalog'}."
            )

        @mcp.prompt(
            name="videoflow_review",
            description="Review QA artifacts and repair the timeline.",
        )
        def review_prompt(project_id: str, job_id: str) -> str:
            return (
                f"Read vf_qa and vf_job(action='logs') for project {project_id} "
                f"job {job_id}. Explain each defect, inspect the frames, and apply only "
                "validated timeline edits."
            )

        @mcp.prompt(
            name="videoflow_deliver",
            description="Build and validate the multi-NLE delivery bundle.",
        )
        def deliver_prompt(project_id: str) -> str:
            return (
                f"Run vf_exports(action='bundle', project_id='{project_id}', targets='all'), "
                "then report the bundle manifest, any missing media, and blocked licenses."
            )

    @mcp.resource("vf://projects")
    def projects_resource() -> str:
        """List registered projects."""

        return json.dumps(
            {"ok": True, "projects": [item.to_dict() for item in list_projects()]},
            indent=2,
        )

    @mcp.resource("vf://projects/{project_id}/state")
    def project_state(project_id: str) -> str:
        """Project state JSON."""

        try:
            record = get_project(project_id)
            state = _state(record)
        except VideoFlowError as exc:
            return _error(exc.code, exc.message)
        return state.model_dump_json(indent=2)

    @mcp.resource("vf://projects/{project_id}/timeline")
    def project_timeline(project_id: str) -> str:
        """Canonical timeline JSON with per-clip source ids."""

        try:
            state = _state(get_project(project_id))
        except VideoFlowError as exc:
            return _error(exc.code, exc.message)
        return json.dumps(
            {
                "ok": True,
                "revision": state.revision,
                "primary_source_id": state.primary_source_id,
                "sources": {
                    key: value.model_dump(mode="json") for key, value in state.sources.items()
                },
                "video": [item.model_dump(mode="json") for item in state.video_segments],
                "audio": [item.model_dump(mode="json") for item in state.audio_segments],
                "overlays": [item.model_dump(mode="json") for item in state.overlays],
            },
            indent=2,
        )

    @mcp.resource("vf://projects/{project_id}/transcript")
    def project_transcript(project_id: str) -> str:
        """Project transcript as SRT."""

        try:
            state = _state(get_project(project_id))
        except VideoFlowError as exc:
            return _error(exc.code, exc.message)
        rate = state.media_info.audio_sample_rate if state.media_info else 48000
        return format_srt(state.transcript, rate)

    @mcp.resource("vf://projects/{project_id}/jobs")
    def project_jobs(project_id: str) -> str:
        """Jobs belonging to one project."""

        try:
            record = get_project(project_id)
        except VideoFlowError as exc:
            return _error(exc.code, exc.message)
        jobs = [
            job.to_dict(summary=True)
            for job in manager.list()
            if getattr(job, "project_id", "") == project_id
            or Path(job.output).expanduser().resolve() == Path(record.output).expanduser().resolve()
        ]
        return json.dumps({"ok": True, "jobs": jobs}, indent=2)

    @mcp.resource("vf://projects/{project_id}/artifacts")
    def project_artifacts(project_id: str) -> str:
        """Artifact manifest for a project."""

        try:
            record = get_project(project_id)
        except VideoFlowError as exc:
            return _error(exc.code, exc.message)
        return json.dumps(
            {"ok": True, "artifacts": list_artifacts(Path(record.output))},
            indent=2,
        )

    @mcp.resource("vf://projects/{project_id}/jobs/{job_id}/logs")
    def job_logs(project_id: str, job_id: str) -> str:
        """Persisted job log."""

        try:
            get_project(project_id)
            job = manager.get(job_id)
        except VideoFlowError as exc:
            return _error(exc.code, exc.message)
        path = Path(job.output) / "job.log"
        if not path.is_file():
            return _error("logs_not_found", "No job.log has been written yet")
        return path.read_text(encoding="utf-8", errors="replace")

    @mcp.resource("vf://styles")
    def styles_catalog() -> str:
        """Canonical Markdown style catalog."""

        from videoflow.application.style_catalog import StyleCatalog

        return json.dumps(
            {"ok": True, "styles": StyleCatalog().list_payload()},
            indent=2,
        )

    @mcp.resource("vf://styles/{style_id}")
    def style_document(style_id: str) -> str:
        """One style definition plus its canonical Markdown."""

        from videoflow.application.style_catalog import (
            StyleCatalog,
            render_style_markdown,
        )

        try:
            catalog = StyleCatalog()
            style = catalog.get(style_id)
        except VideoFlowError as exc:
            return _error(exc.code, exc.message)
        return json.dumps(
            {
                "ok": True,
                "style": style.model_dump(mode="json"),
                "markdown": render_style_markdown(style),
                "file_path": str(catalog.path_for(style.style_id)),
            },
            indent=2,
        )

    @mcp.resource("vf://presets/{channel_id}/rulebook")
    def preset_rulebook(channel_id: str) -> str:
        """Active channel rulebook with hard constraints and learned rules."""

        return load_rulebook(channel_id).model_dump_json(indent=2)

    @mcp.resource("vf://presets/{channel_id}/kit")
    def channel_kit(channel_id: str) -> str:
        """Channel asset kit."""

        return load_rulebook(channel_id).channel_kit.model_dump_json(indent=2)

    @mcp.resource("vf://docs/steps")
    def steps_catalog() -> str:
        """Full catalog of node/tool types."""

        from videoflow.steps.registry import iter_steps

        return json.dumps(
            {
                "ok": True,
                "steps": [
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
                ],
            },
            indent=2,
        )

    @mcp.resource("vf://docs/steps/{step_type}")
    def step_docs(step_type: str) -> str:
        """Full parameter schema for one step type."""

        try:
            step = get_step(step_type)
        except VideoFlowError as exc:
            return _error(exc.code, exc.message)
        return json.dumps(
            {
                "type": step.type,
                "title": step.title,
                "description": step.description,
                "status": step.status,
                "requires": list(step.requires),
                "produces": list(step.produces),
                "schema": step.params_model.model_json_schema(),
            },
            indent=2,
        )
