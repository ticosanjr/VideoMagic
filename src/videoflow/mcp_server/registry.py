"""Public MCP surface for the agent profile.

The agent profile is deliberately small: project-scoped tools, explicit ids, and
on-demand resources for step/recipe schemas. The old 82-tool UI surface is not
registered here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    module: str


@dataclass(frozen=True, slots=True)
class ResourceSpec:
    uri: str
    description: str


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "vf_project_init",
        "Create or adopt a project and return its stable project_id.",
        "project",
    ),
    ToolSpec(
        "vf_project_status",
        "Return project state, jobs, artifacts, and resource links.",
        "project",
    ),
    ToolSpec(
        "vf_capabilities",
        "Return backend, model, and external-provider availability.",
        "system",
    ),
    ToolSpec(
        "vf_list_recipes",
        "List built-in recipes.",
        "recipes",
    ),
    ToolSpec(
        "vf_get_recipe",
        "Return one complete recipe document.",
        "recipes",
    ),
    ToolSpec(
        "vf_validate_recipe",
        "Validate a recipe DAG and return its execution order.",
        "recipes",
    ),
    ToolSpec(
        "vf_run_recipe",
        "Run a named or inline recipe in one project.",
        "recipes",
    ),
    ToolSpec(
        "vf_get_job",
        "Return one job with artifacts and QA summary.",
        "jobs",
    ),
    ToolSpec(
        "vf_wait_job",
        "Wait for a job to finish with a bounded timeout.",
        "jobs",
    ),
    ToolSpec(
        "vf_get_step_logs",
        "Return bounded step logs, commands, timing, and memory.",
        "jobs",
    ),
    ToolSpec(
        "vf_get_qa_artifacts",
        "Return QA defects, frame paths, and optional image content.",
        "qa",
    ),
    ToolSpec(
        "vf_get_timeline",
        "Return the canonical timeline with per-clip source ids.",
        "timeline",
    ),
    ToolSpec(
        "vf_edit_timeline",
        "Edit one clip with optimistic revision concurrency.",
        "timeline",
    ),
    ToolSpec(
        "vf_get_transcript",
        "Return the structured transcript and SRT.",
        "transcript",
    ),
    ToolSpec(
        "vf_get_artifact",
        "Return artifact metadata and image content when applicable.",
        "artifacts",
    ),
    ToolSpec(
        "vf_edit_short",
        "Trim, retitle, reframe, and re-render one Short.",
        "shorts",
    ),
    ToolSpec(
        "vf_nle_roundtrip",
        "Push or pull cuts and markers through FCPXML/MLT or Resolve.",
        "nle",
    ),
    ToolSpec(
        "vf_validate_exports",
        "Validate exported FCPXML, XMEML, and Kdenlive files.",
        "nle",
    ),
    ToolSpec(
        "vf_respond_interaction",
        "Answer a HITL request and resume the job.",
        "hitl",
    ),
    ToolSpec(
        "vf_ingest_session",
        "Order and normalize a multi-take recording session.",
        "ingest",
    ),
    ToolSpec(
        "vf_sync_multicam",
        "Synchronize two sources by audio cross-correlation.",
        "ingest",
    ),
    ToolSpec(
        "vf_render_start",
        "Start a timeline or preview render job.",
        "render",
    ),
)

RESOURCE_SPECS: tuple[ResourceSpec, ...] = (
    ResourceSpec("vf://projects", "Registered projects."),
    ResourceSpec("vf://projects/{project_id}/state", "Project state JSON."),
    ResourceSpec("vf://projects/{project_id}/timeline", "Canonical timeline JSON."),
    ResourceSpec("vf://projects/{project_id}/transcript", "Project transcript SRT."),
    ResourceSpec("vf://projects/{project_id}/jobs", "Jobs for one project."),
    ResourceSpec("vf://projects/{project_id}/artifacts", "Artifact manifest."),
    ResourceSpec("vf://projects/{project_id}/jobs/{job_id}/logs", "Persisted job log."),
    ResourceSpec("vf://presets/{channel_id}/rulebook", "Active channel rulebook."),
    ResourceSpec("vf://presets/{channel_id}/kit", "Channel asset kit."),
    ResourceSpec("vf://docs/steps/{step_type}", "Full step parameter schema."),
    ResourceSpec("vf://docs/recipes/{recipe_id}", "Complete recipe document."),
)
