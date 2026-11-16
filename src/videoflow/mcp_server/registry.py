"""Public MCP surface for the 2.90 core profile.

Twelve tools, explicit project ids, and on-demand resources for the 122+ step
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
        "Search steps and recipes without loading their schemas.",
        "catalog",
    ),
    ToolSpec(
        "vf_exec",
        "Run a recipe or edit a Short; catalog steps remain an internal path.",
        "recipes",
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
    ResourceSpec("vf://presets/{channel_id}/rulebook", "Active channel rulebook."),
    ResourceSpec("vf://presets/{channel_id}/kit", "Channel asset kit."),
    ResourceSpec("vf://docs/steps/{step_type}", "Full step parameter schema."),
    ResourceSpec("vf://docs/recipes/{recipe_id}", "Complete recipe document."),
)
