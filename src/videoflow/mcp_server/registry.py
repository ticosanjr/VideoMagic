"""Public MCP surface for the 3.5 core profile.

One tool per workflow area with explicit ``action`` values, stable project ids,
and on-demand resources for the step catalog. Fetch, audio and vision
capabilities live in ``videoflow.domains`` and are exposed by this same server;
the GPU worker remains a separate remote runtime.
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
        "Render overlay boxes or a crop rectangle preview frame.",
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
        "vf_depth_composite",
        "Place text or graphics behind a matted presenter in one time range.",
        "compositor",
    ),
    ToolSpec(
        "vf_pip",
        "Add a rounded-window picture-in-picture overlay.",
        "compositor",
    ),
    ToolSpec(
        "vf_parallax",
        "Animate a still as background plus subject 2.5D parallax.",
        "compositor",
    ),
    ToolSpec(
        "vf_style_preview",
        "Render a short style card with palette, font, layout, and caption.",
        "compositor",
    ),
    ToolSpec(
        "vf_fx_depth",
        "Composite text or graphics behind a matted presenter with real alpha.",
        "compositor",
    ),
    ToolSpec(
        "vf_fx_parallax",
        "Animate a still as background plus a real-alpha 2.5D subject.",
        "compositor",
    ),
    ToolSpec(
        "vf_fx_motion",
        "Render HTML, HyperFrames, Remotion, Manim, or FFmpeg motion graphics.",
        "compositor",
    ),
    ToolSpec(
        "vf_fx_capture",
        "Capture a URL or screen as a still or a scrollable B-roll clip.",
        "compositor",
    ),
    ToolSpec(
        "vf_media",
        "Fetch stock media, animate stills, generate beds, and audit or clear licenses.",
        "assets",
    ),
    ToolSpec(
        "vf_audio",
        "TTS, voice cleanup, stem separation, music/Foley, and audio mastering.",
        "audio",
    ),
    ToolSpec(
        "vf_vision",
        "Word-aligned captions, background removal, and image/video upscaling.",
        "vision",
    ),
    ToolSpec(
        "vf_font",
        "List or resolve bundled, system, fontconfig, and aliased fonts.",
        "assets",
    ),
    ToolSpec(
        "vf_preview",
        "Render ordered caption or overlay preview frames.",
        "qa",
    ),
    ToolSpec(
        "vf_shorts_batch",
        "Render multiple Shorts with per-clip style, crop, intro, and music.",
        "shorts",
    ),
    ToolSpec(
        "vf_format",
        "List, get, save, delete, or duplicate output format presets.",
        "formats",
    ),
    ToolSpec(
        "vf_scenes",
        "Analyze scenes or read the cached manifest, keyframe metadata, supercontext, and cache.",
        "scenes",
    ),
    ToolSpec(
        "vf_qa_final",
        "Audit the deliverable MP4, safe zones, loudness, and contact sheet.",
        "qa",
    ),
    ToolSpec(
        "vf_qa_compare",
        "Compare two immutable QA reports for regressions.",
        "qa",
    ),
    ToolSpec(
        "vf_transcript_query",
        "Search or page through the cleaned transcript without dumping it.",
        "transcript",
    ),
    ToolSpec(
        "vf_glossary",
        "List, update, or apply a channel glossary of technical terms.",
        "transcript",
    ),
    ToolSpec(
        "vf_storyboard_strip",
        "Render one contact-sheet PNG for a timeline or source range.",
        "qa",
    ),
    ToolSpec(
        "vf_preflight_plan",
        "Validate schema, dependencies, licenses, disk, GPU, and cost.",
        "system",
    ),
    ToolSpec(
        "vf_assets",
        "List assets, licenses, or fonts; approve, quarantine, or register fonts.",
        "assets",
    ),
    ToolSpec(
        "vf_project",
        "Create/open/status a project, brief the session, and manage checkpoints.",
        "project",
    ),
    ToolSpec(
        "vf_capabilities",
        "Return backend, model, and external-provider availability.",
        "system",
    ),
    ToolSpec(
        "vf_gpu_preflight",
        "Validate the Windows GPU worker before a long job.",
        "system",
    ),
    ToolSpec(
        "vf_catalog_search",
        "List or search node/tool types without loading their schemas.",
        "catalog",
    ),
    ToolSpec(
        "vf_style",
        "List, get, create, save, duplicate, restore, sync, analyze, delete, "
        "or learn rules for Markdown styles.",
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
        "vf_job",
        "List, cancel, get, wait, inspect logs, or read QA for a job.",
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
        "vf_export",
        "Bundle, draft-render, validate, or NLE-roundtrip exports.",
        "nle",
    ),
    ToolSpec(
        "vf_interaction",
        "List, read, or answer human-in-the-loop requests.",
        "hitl",
    ),
    ToolSpec(
        "vf_ingest",
        "Run session ingest, multicam synchronization, or audio diagnosis.",
        "ingest",
    ),
)

RESOURCE_SPECS: tuple[ResourceSpec, ...] = (
    ResourceSpec("vf://projects", "Registered projects."),
    ResourceSpec("vf://projects/{project_id}/state", "Project state JSON."),
    ResourceSpec("vf://projects/{project_id}/timeline", "Canonical timeline JSON."),
    ResourceSpec("vf://projects/{project_id}/transcript", "Project transcript SRT."),
    ResourceSpec("vf://projects/{project_id}/jobs", "Jobs for one project."),
    ResourceSpec("vf://projects/{project_id}/artifacts", "Artifact manifest."),
    ResourceSpec("vf://projects/{project_id}/scenes", "Cached scene manifest."),
    ResourceSpec(
        "vf://projects/{project_id}/scenes/{scene_id}/keyframe",
        "Scene keyframe metadata and file path.",
    ),
    ResourceSpec("vf://projects/{project_id}/jobs/{job_id}/logs", "Persisted job log."),
    ResourceSpec("vf://styles", "Canonical Markdown style catalog."),
    ResourceSpec("vf://styles/{style_id}", "One Markdown style and its rules."),
    ResourceSpec("vf://presets/{channel_id}/rulebook", "Active channel rulebook."),
    ResourceSpec("vf://presets/{channel_id}/kit", "Channel asset kit."),
    ResourceSpec("vf://docs/steps", "Full node/tool catalog."),
    ResourceSpec("vf://docs/steps/{step_type}", "Full step parameter schema."),
    ResourceSpec("vf://docs/contracts/{name}", "One short media/QA contract document."),
)
