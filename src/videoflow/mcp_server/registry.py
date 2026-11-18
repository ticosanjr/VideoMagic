"""Public MCP surface for the 2.90 core profile.

Thirteen tools, explicit project ids, and on-demand resources for the 122+ step
catalog. Domain capabilities live in the separate vf-fetch, vf-audio, vf-vision,
and vf-gpu-worker packages.
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
        "vf_style_list",
        "List the Markdown style catalog and optional workspace sync.",
        "styles",
    ),
    ToolSpec(
        "vf_style_save",
        "Create or update one Markdown style and sync presets/.",
        "styles",
    ),
    ToolSpec(
        "vf_style_learn_rule",
        "Append review rules to one style, capped at 15 consolidated rules.",
        "styles",
    ),
    ToolSpec(
        "analyze_reference_style",
        "Analyze a reference and return a style candidate without saving.",
        "styles",
    ),
    ToolSpec(
        "vf_style_validate",
        "Validate caption presets, layouts, motion engines, and fonts in a style.",
        "styles",
    ),
    ToolSpec(
        "vf_style_apply",
        "Compile a style into pipeline parameters, a beat-map draft, and a diff.",
        "styles",
    ),
    ToolSpec(
        "vf_beatmap_plan",
        "Build a structured beat-map draft from the transcript and a style.",
        "timeline",
    ),
    ToolSpec(
        "vf_overlay",
        "Insert an image or video overlay by source or timeline time.",
        "timeline",
    ),
    ToolSpec(
        "vf_overlay_preview",
        "Render one frame with overlay boxes, captions, safe zones, and labels.",
        "timeline",
    ),
    ToolSpec(
        "vf_layout",
        "Auto-pack overlay margins and write an auditable layout.json.",
        "timeline",
    ),
    ToolSpec(
        "vf_caption_preview",
        "Render before/during/after frames for the active caption.",
        "qa",
    ),
    ToolSpec(
        "vf_qa_autofix",
        "Resolve overlay/caption collisions and persist the corrected layout.",
        "qa",
    ),
    ToolSpec(
        "vf_shorts_batch",
        "Render multiple Shorts with per-clip style, crop, intro, and music.",
        "shorts",
    ),
    ToolSpec(
        "vf_qa_final",
        "Audit the deliverable MP4, safe zones, loudness, and contact sheet.",
        "qa",
    ),
    ToolSpec(
        "vf_font",
        "List, register, or install TTF/OTF fonts.",
        "assets",
    ),
    ToolSpec(
        "vf_project",
        "Create/open/status a project, clone a channel style, or learn a rule.",
        "project",
    ),
    ToolSpec(
        "vf_capabilities",
        "Return backend, model, and external-provider availability.",
        "system",
    ),
    ToolSpec(
        "vf_catalog_search",
        "List or search node/tool types without loading their schemas.",
        "catalog",
    ),
    ToolSpec(
        "vf_style",
        "List, save, sync, or learn rules for Markdown channel styles.",
        "styles",
    ),
    ToolSpec(
        "vf_exec",
        "Run one catalog step or edit a Short. Recipes are not exposed via MCP.",
        "steps",
    ),
    ToolSpec(
        "vf_run",
        "Run an ordered, linear chain of catalog steps with persisted checkpoints.",
        "steps",
    ),
    ToolSpec(
        "vf_jobs",
        "List, inspect, or cancel jobs in the shared SQLite queue.",
        "jobs",
    ),
    ToolSpec(
        "vf_job",
        "Get, wait, inspect logs, or read QA for a job.",
        "jobs",
    ),
    ToolSpec(
        "vf_timeline",
        "Read, edit, or atomically apply a beatmap to the canonical timeline.",
        "timeline",
    ),
    ToolSpec(
        "vf_artifact",
        "List or read project artifacts, including image content.",
        "artifacts",
    ),
    ToolSpec(
        "vf_render",
        "Start, inspect, or cancel a render job.",
        "render",
    ),
    ToolSpec(
        "vf_export",
        "Render the canonical MP4 master and requested NLE delivery targets.",
        "nle",
    ),
    ToolSpec(
        "vf_crop_preview",
        "Extract a frame with the normalized crop rectangle and thirds grid.",
        "timeline",
    ),
    ToolSpec(
        "vf_exports",
        "Export a multi-NLE bundle, validate it, or run an NLE roundtrip.",
        "nle",
    ),
    ToolSpec(
        "vf_interaction",
        "List, read, or answer human-in-the-loop requests.",
        "hitl",
    ),
    ToolSpec(
        "vf_ingest",
        "Run session ingest or multicam synchronization.",
        "ingest",
    ),
    ToolSpec(
        "vf_qa",
        "Read QA artifacts or route new QA runs through vf_exec.",
        "qa",
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
    ResourceSpec("vf://styles", "Canonical Markdown style catalog."),
    ResourceSpec("vf://styles/{style_id}", "One Markdown style and its rules."),
    ResourceSpec("vf://presets/{channel_id}/rulebook", "Active channel rulebook."),
    ResourceSpec("vf://presets/{channel_id}/kit", "Channel asset kit."),
    ResourceSpec("vf://docs/steps", "Full node/tool catalog."),
    ResourceSpec("vf://docs/steps/{step_type}", "Full step parameter schema."),
)
