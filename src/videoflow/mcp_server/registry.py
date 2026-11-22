"""MCP tool registry and strict v4.2 profiles.

``core`` exposes exactly 16 tools and ``full`` exactly 21. The internal ``all``
profile keeps every granular tool for the HTTP API and compatibility tests.
Fetch, audio and vision capabilities live in ``videoflow.domains`` and are
exposed by this same server; the GPU worker remains a separate remote runtime.
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
    ToolSpec(
        "vf_session_brief",
        "Summarize a project's stage, sources, GPU, QA, and next moves.",
        "project",
    ),
    ToolSpec(
        "vf_transcript",
        "Search, page, and maintain the cleaned transcript and glossary.",
        "transcript",
    ),
    ToolSpec(
        "vf_decupage",
        "Plan the beat map and assemble the canonical decupage timeline.",
        "timeline",
    ),
    ToolSpec(
        "vf_shorts",
        "Batch-render Shorts with per-clip style, crop, intro, and music.",
        "shorts",
    ),
    ToolSpec(
        "vf_qa",
        "Audit the deliverable, compare QA runs, and autofix layout defects.",
        "qa",
    ),
    ToolSpec(
        "vf_jobs",
        "List, cancel, wait, inspect logs, or read QA for project jobs.",
        "jobs",
    ),
)

# Official v4.2 profiles. ``all`` is internal and keeps every granular tool for
# the HTTP API and backward-compatible tests; the CLI only accepts core/full.
CORE_TOOL_NAMES: tuple[str, ...] = (
    "vf_project",
    "vf_session_brief",
    "vf_capabilities",
    "vf_ingest",
    "vf_run",
    "vf_transcript",
    "vf_decupage",
    "vf_scenes",
    "vf_preview",
    "vf_timeline",
    "vf_shorts",
    "vf_audio",
    "vf_media",
    "vf_export",
    "vf_qa",
    "vf_jobs",
)

FULL_TOOL_NAMES: tuple[str, ...] = (
    *CORE_TOOL_NAMES,
    "vf_fx_depth",
    "vf_fx_parallax",
    "vf_fx_motion",
    "vf_fx_capture",
    "vf_style",
)

PROFILE_TOOL_NAMES: dict[str, tuple[str, ...]] = {
    "core": CORE_TOOL_NAMES,
    "full": FULL_TOOL_NAMES,
    "all": tuple(spec.name for spec in TOOL_SPECS),
}


def profile_tool_names(profile: str) -> tuple[str, ...]:
    """Return the exact tool list for one profile."""

    try:
        return PROFILE_TOOL_NAMES[str(profile).strip().lower()]
    except KeyError as exc:
        raise ValueError(f"unknown MCP profile: {profile!r}") from exc


TOOL_DOCSTRINGS: dict[str, str] = {
    "vf_project": (
        "[DOES] Create, open, or inspect a project and manage checkpoints.\n"
        "[REQUIRES] ``action`` plus the project path or ``project_id``.\n"
        "[RETURNS] Project record, summary, or checkpoint metadata."
    ),
    "vf_session_brief": (
        "[DOES] Summarize stage, sources, GPU, QA, and revision for a session.\n"
        "[REQUIRES] A registered ``project_id``.\n"
        "[RETURNS] Compact brief with next actions and recent revisions."
    ),
    "vf_capabilities": (
        "[DOES] Report backend, model, and external-provider availability.\n"
        "[REQUIRES] Optional ``allow_external_services``.\n"
        "[RETURNS] Capability list plus policy flags."
    ),
    "vf_ingest": (
        "[DOES] Ingest sources, synchronize multicam, or diagnose audio.\n"
        "[REQUIRES] ``action`` and project sources or a ``project_id``.\n"
        "[RETURNS] Job payload or the updated session state."
    ),
    "vf_run": (
        "[DOES] Run an ordered chain of catalog steps with checkpoints.\n"
        "[REQUIRES] ``project_id`` and an explicit step list.\n"
        "[RETURNS] Job payload with per-step status and artifacts."
    ),
    "vf_transcript": (
        "[DOES] Search or page the transcript and maintain the glossary.\n"
        "[REQUIRES] ``project_id`` and a query or glossary action.\n"
        "[RETURNS] Matching transcript spans or the updated glossary."
    ),
    "vf_decupage": (
        "[DOES] Plan a beat map and assemble the canonical decupage timeline.\n"
        "[REQUIRES] ``project_id``, style parameters, and a time range.\n"
        "[RETURNS] Beat-map plan or the applied timeline revision."
    ),
    "vf_scenes": (
        "[DOES] Analyze scenes or read the cached scene manifest.\n"
        "[REQUIRES] ``project_id`` and an optional cache or analyze action.\n"
        "[RETURNS] Scene summary, manifest, or keyframe metadata."
    ),
    "vf_preview": (
        "[DOES] Render ordered caption or overlay preview frames.\n"
        "[REQUIRES] ``project_id`` and preview times or target artifacts.\n"
        "[RETURNS] Preview image paths and their timeline times."
    ),
    "vf_timeline": (
        "[DOES] Read, edit, or atomically apply a beat map to the timeline.\n"
        "[REQUIRES] ``project_id``, ``action``, and edit or beat-map fields.\n"
        "[RETURNS] Canonical timeline JSON or the new revision."
    ),
    "vf_shorts": (
        "[DOES] Batch-render Shorts with style, crop, intro, and music.\n"
        "[REQUIRES] ``project_id`` and clip or source ranges.\n"
        "[RETURNS] Job payload with rendered Short paths."
    ),
    "vf_audio": (
        "[DOES] Run TTS, cleanup, stems, music, Foley, and mastering.\n"
        "[REQUIRES] ``action`` plus the audio source or text.\n"
        "[RETURNS] Audio artifact path and execution metadata."
    ),
    "vf_media": (
        "[DOES] Fetch stock media, animate stills, and audit licenses.\n"
        "[REQUIRES] ``action`` and a query, image, or asset id.\n"
        "[RETURNS] Media artifact paths, animation, or license report."
    ),
    "vf_export": (
        "[DOES] Bundle, draft-render, validate, or NLE-roundtrip exports.\n"
        "[REQUIRES] ``project_id`` and an export action or targets.\n"
        "[RETURNS] Job payload with exports, checks, and roundtrip paths."
    ),
    "vf_qa": (
        "[DOES] Audit the deliverable, compare QA runs, and autofix layout.\n"
        "[REQUIRES] ``project_id`` and a QA action or report ids.\n"
        "[RETURNS] QA report, regression diff, or corrected layout."
    ),
    "vf_jobs": (
        "[DOES] List, cancel, wait, inspect logs, or read QA for jobs.\n"
        "[REQUIRES] ``action`` and optional ``project_id`` or ``job_id``.\n"
        "[RETURNS] Job records, logs, or persisted QA artifacts."
    ),
    "vf_fx_depth": (
        "[DOES] Composite text or graphics behind a matted presenter.\n"
        "[REQUIRES] ``project_id``, the asset, and a time range.\n"
        "[RETURNS] Timeline layers with alpha and overlay metadata."
    ),
    "vf_fx_parallax": (
        "[DOES] Animate a still as background plus real-alpha 2.5D subject.\n"
        "[REQUIRES] ``project_id``, an image, and a time range.\n"
        "[RETURNS] Parallax layers written to the timeline."
    ),
    "vf_fx_motion": (
        "[DOES] Render HTML, HyperFrames, Remotion, Manim, or FFmpeg motion.\n"
        "[REQUIRES] A project, motion source, engine, and duration.\n"
        "[RETURNS] Rendered motion artifact and overlay metadata."
    ),
    "vf_fx_capture": (
        "[DOES] Capture a URL or screen as a still or scrollable B-roll.\n"
        "[REQUIRES] A ``url`` or screen target and capture mode.\n"
        "[RETURNS] Captured image or video clip path."
    ),
    "vf_style": (
        "[DOES] List, save, sync, analyze, or learn rules for styles.\n"
        "[REQUIRES] ``action`` and a style id or Markdown payload.\n"
        "[RETURNS] Style record, diff, validation, or learned rules."
    ),
}


def validate_tool_docstring(func: object) -> None:
    """Fail registration when a tool has no three-line MCP contract."""

    doc = str(getattr(func, "__doc__", "") or "").strip()
    lines = [line for line in doc.splitlines() if line.strip()]
    missing = [
        marker
        for marker in ("[DOES]", "[REQUIRES]", "[RETURNS]")
        if marker not in doc
    ]
    if missing or len(lines) < 3:
        name = getattr(func, "__name__", repr(func))
        raise RuntimeError(
            f"MCP tool {name} needs a three-line [DOES]/[REQUIRES]/[RETURNS] "
            f"docstring; missing {missing or 'three lines'}"
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
