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
from videoflow.application.scene_intel.store import latest_scene_snapshot
from videoflow.domain.errors import VideoFlowError
from videoflow.domain.transcript import format_srt
from videoflow.steps.registry import get_step


def _state(record: ProjectRecord):
    return load_project_state(record)


def _error(code: str, message: str) -> str:
    return json.dumps({"ok": False, "code": code, "message": message})


def contracts_dir() -> Path:
    import sys

    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled) / "docs" / "contracts"
    repo = Path(__file__).resolve().parents[3]
    installed = Path(__file__).resolve().parents[1] / "contracts"
    if (repo / "docs" / "contracts").is_dir():
        return repo / "docs" / "contracts"
    if installed.is_dir():
        return installed
    return repo / "docs" / "contracts"


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
                f"Read vf_job(action='qa') and vf_job(action='logs') for project {project_id} "
                f"job {job_id}. Explain each defect, inspect the frames, and apply only "
                "validated timeline edits."
            )

        @mcp.prompt(
            name="videoflow_deliver",
            description="Build and validate the multi-NLE delivery bundle.",
        )
        def deliver_prompt(project_id: str) -> str:
            return (
                f"Run vf_export(project_id='{project_id}', targets='all'), "
                "then optionally run vf_exec(action='step', "
                "step_id='delivery.collect', params={'mode':'copy'}) to group "
                "final videos and exports under VideoFlow_Output when the user "
                "did not choose another destination. Never treat that folder as "
                "a validation requirement; the MCP accepts any output path. "
                "Report the bundle manifest, any missing media, any degraded "
                "heavy-compute fallback, and blocked licenses."
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

    @mcp.resource("vf://projects/{project_id}/scenes")
    def project_scenes(project_id: str) -> str:
        """Cached scene manifest with keyframe paths."""

        try:
            record = get_project(project_id)
        except VideoFlowError as exc:
            return _error(exc.code, exc.message)
        snapshot = latest_scene_snapshot(Path(record.output))
        if snapshot is None:
            return _error(
                "scenes_missing",
                "Run vf_scenes(action='analyze') to build the scene manifest",
            )
        return json.dumps(
            {
                "ok": True,
                "summary": snapshot.summary(),
                "manifest": snapshot.manifest.model_dump(mode="json"),
            },
            indent=2,
        )

    @mcp.resource("vf://projects/{project_id}/scenes/{scene_id}/keyframe")
    def project_scene_keyframe(project_id: str, scene_id: str) -> str:
        """Keyframe metadata and path; image bytes stay out of the resource."""

        try:
            record = get_project(project_id)
        except VideoFlowError as exc:
            return _error(exc.code, exc.message)
        snapshot = latest_scene_snapshot(Path(record.output))
        if snapshot is None:
            return _error("scenes_missing", "No cached scene manifest")
        item = snapshot.keyframe(scene_id)
        if item is None:
            return _error("scene_not_found", f"Scene {scene_id} is not cached")
        return json.dumps(
            {"ok": True, **item, "image_returned": False},
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
    def brand_kit(channel_id: str) -> str:
        """Channel asset kit plus the optional brands/{channel_id} bundle."""

        from videoflow.application.brand_kit import load_brand_kit

        payload = load_rulebook(channel_id).brand_kit.model_dump(mode="json")
        payload["brand_kit"] = load_brand_kit(channel_id)
        return json.dumps(payload, indent=2)

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
        schema = step.params_model.model_json_schema()
        properties = schema.get("properties") or {}
        defaults = {
            key: value["default"]
            for key, value in properties.items()
            if isinstance(value, dict) and "default" in value
        }
        example = dict(defaults)
        for key in schema.get("required") or []:
            if key not in example:
                value = properties.get(key) or {}
                kind = value.get("type")
                example[key] = (
                    ""
                    if kind == "string"
                    else 0
                    if kind in {"integer", "number"}
                    else False
                    if kind == "boolean"
                    else []
                    if kind == "array"
                    else {}
                )
        return json.dumps(
            {
                "type": step.type,
                "title": step.title,
                "description": step.description,
                "status": step.status,
                "requires": list(step.requires),
                "produces": list(step.produces),
                "schema": schema,
                "defaults": defaults,
                "example": example,
            },
            indent=2,
        )

    @mcp.resource("vf://docs/contracts/{name}")
    def contract_docs(name: str) -> str:
        """One short contract document from docs/contracts."""

        root = contracts_dir().resolve()
        candidate = (root / f"{Path(str(name)).name}.md").resolve()
        if root not in candidate.parents:
            return _error("invalid_contract", "contract name escapes docs/contracts")
        if not candidate.is_file():
            return _error("contract_not_found", f"Unknown contract: {name}")
        return candidate.read_text(encoding="utf-8", errors="replace")
