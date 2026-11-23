"""Validate an operation and estimate remote/local cost before running it."""

from __future__ import annotations

import difflib
import shutil
from pathlib import Path
from typing import Any

from videoflow.application.compute import compute_status
from videoflow.application.projects import get_project, load_project_state
from videoflow.domains.media import license_blockers

KNOWN_FIELDS: dict[str, set[str]] = {
    "export": {
        "targets",
        "look",
        "audio_source",
        "captions",
        "draft",
        "release_kit",
        "fps",
        "qa_mode",
        "preset",
    },
    "shorts_batch": {"clips"},
    "depth_composite": {
        "text_or_asset",
        "start_sec",
        "end_sec",
        "anchor",
        "margin_x",
        "margin_y",
        "z",
    },
    "transcribe": {
        "mode",
        "model_id",
        "language",
        "device",
        "compute_type",
        "quality_profile",
    },
    "ingest": {
        "sources",
        "raw_dir",
        "order",
        "target_fps",
        "target_width",
        "target_height",
        "normalize",
    },
    "decupage": {
        "preset",
        "llm_policy",
        "compute_policy",
        "language",
        "targets",
        "render",
        "export_fcpxml",
        "export_otio",
    },
    "scenes": {
        "video_path",
        "decupagem_plan_path",
        "source_topology",
        "threshold",
        "min_scene_len_sec",
        "compute_policy",
    },
    "shorts_compose": {
        "short_id",
        "start_sec",
        "end_sec",
        "plan_path",
        "llm_policy",
        "compute_policy",
        "export_fcpxml",
        "render_mp4",
    },
}

ESTIMATES: dict[str, tuple[float, float]] = {
    "export": (1.5, 0.5),
    "shorts_batch": (60.0, 20.0),
    "depth_composite": (20.0, 5.0),
    "transcribe": (0.35, 0.03),
    "ingest": (0.05, 0.05),
    "decupage": (0.55, 0.08),
    "scenes": (0.02, 0.01),
    "shorts_compose": (0.40, 0.04),
}

PLANS: dict[str, list[str]] = {
    "export": ["audio.finalize", "vf_export", "vf_qa_final"],
    "shorts_batch": ["vf_shorts_batch", "vf_qa_final"],
    "depth_composite": ["vf_depth_composite", "vf_qa_final"],
    "transcribe": ["vf_exec(transcribe)", "vf_transcript_query"],
    "ingest": ["vf_ingest", "vf_transcript_query"],
    "decupage": [
        "audio.events",
        "audio.vad",
        "transcribe",
        "alignment.forced",
        "speech.asu",
        "decupage.prefilter",
        "decupage.llm",
        "decupage.apply",
        "decupage.snap",
        "decupage.timeline",
        "export.nle",
    ],
    "scenes": [
        "scene.proxy",
        "scene.detect",
        "scene.layout",
        "scene.keyframes",
        "scene.supercontext",
    ],
    "shorts_compose": [
        "short.plan",
        "short.captions",
        "short.validate",
        "short.render",
        "short.export",
        "short.qa",
    ],
}


DECUPAGE_STAGES = (
    ("ingest", "cpu_light", "local", ""),
    ("audio.vad", "cpu_light", "local", ""),
    ("audio.events", "cpu_heavy", "local", ""),
    ("transcribe", "gpu_asr", "remote", "asr"),
    ("alignment.forced", "gpu_align", "remote", "forced_align"),
    ("speech.asu", "cpu_light", "local", ""),
    ("decupage.prefilter", "cpu_light", "local", ""),
    ("decupage.llm", "llm", "llm", ""),
    ("decupage.apply", "cpu_light", "local", ""),
    ("decupage.snap", "cpu_light", "local", ""),
    ("decupage.timeline", "cpu_light", "local", ""),
    ("export.nle", "gpu_render", "remote", "render_nvenc"),
)

SCENE_STAGES = (
    ("scene.proxy", "cpu_light", "local", ""),
    ("scene.detect", "cpu_heavy", "remote", "scene_analyze"),
    ("scene.layout", "cpu_heavy", "remote", "scene_analyze"),
    ("scene.keyframes", "cpu_light", "local", ""),
    ("scene.supercontext", "cpu_light", "local", ""),
)

SHORTS_STAGES = (
    ("short.plan", "llm", "llm", ""),
    ("short.captions", "cpu_light", "local", ""),
    ("short.validate", "cpu_light", "local", ""),
    ("short.render", "gpu_render", "remote", "short_render"),
    ("short.export", "cpu_heavy", "local", ""),
    ("short.qa", "cpu_light", "local", ""),
)

OP_STAGES = {
    "decupage": DECUPAGE_STAGES,
    "scenes": SCENE_STAGES,
    "shorts_compose": SHORTS_STAGES,
}


def _compute_plan(operation: str, gpu: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    stages_definition = OP_STAGES.get(operation)
    if stages_definition is None:
        return {}
    policy = str(params.get("compute_policy") or "auto")
    remote = bool(gpu.get("available")) and policy not in {
        "local",
        "local_gpu",
        "local_only",
    }
    capabilities = set(gpu.get("capabilities") or [])
    stages: list[dict[str, Any]] = []
    for stage, kind, preferred, capability in stages_definition:
        if kind == "llm":
            stages.append(
                {
                    "stage": stage,
                    "class": kind,
                    "preferred": "llm",
                    "placement": "llm",
                    "degraded": False,
                    "reason": "requires an LLM contract",
                }
            )
            continue
        can_remote = (
            preferred == "remote"
            and remote
            and (not capability or capability in capabilities)
        )
        placement = "remote_gpu" if can_remote else "local"
        degraded = (
            preferred == "remote"
            and not can_remote
            and policy not in {"local", "local_gpu", "local_only"}
        )
        stages.append(
            {
                "stage": stage,
                "class": kind,
                "preferred": preferred,
                "placement": placement,
                "degraded": degraded,
                "reason": ""
                if can_remote or preferred == "local"
                else "worker unavailable or capability disabled",
            }
        )
    return {
        "policy": policy,
        "remote_available": bool(gpu.get("available")),
        "degraded": any(item["degraded"] for item in stages),
        "stages": stages,
    }


def _unknown_keys(operation: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    allowed = KNOWN_FIELDS.get(operation)
    if allowed is None:
        return []
    warnings: list[dict[str, Any]] = []
    for key in params:
        if key in allowed:
            continue
        suggestion = difflib.get_close_matches(key, sorted(allowed), n=1)
        warnings.append(
            {
                "code": "unknown_param",
                "key": key,
                "message": f"unknown parameter {key!r} for {operation}",
                "suggestion": suggestion[0] if suggestion else "",
            }
        )
    return warnings


def _duration_sec(state: Any) -> float:
    media = state.media_info
    if media is None or not media.fps_den:
        return 0.0
    return media.duration_frames / (media.fps_num / media.fps_den)


def _dependencies(operation: str, state: Any, params: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    media = state.media_info
    if operation != "ingest" and media is None:
        blockers.append(
            {
                "code": "media_required",
                "message": "project has no ingested media",
                "fix": "run vf_ingest first",
            }
        )
    if operation in {"export", "depth_composite"} and not state.video_segments:
        blockers.append(
            {
                "code": "timeline_required",
                "message": "project has no timeline",
                "fix": "run vf_beatmap_plan and vf_timeline(apply_beatmap)",
            }
        )
    if operation == "shorts_batch":
        if not state.transcript:
            blockers.append(
                {
                    "code": "transcript_required",
                    "message": "project has no transcript",
                    "fix": "run vf_exec(transcribe)",
                }
            )
        clips = params.get("clips")
        if not isinstance(clips, list) or not clips:
            blockers.append(
                {
                    "code": "clips_required",
                    "message": "shorts_batch needs a non-empty clips list",
                    "fix": "build clips with vf_transcript_query or vf_beatmap_plan",
                }
            )
    if operation == "transcribe" and media is None:
        blockers.append(
            {
                "code": "media_required",
                "message": "transcription needs an ingested source",
                "fix": "run vf_ingest first",
            }
        )
    if operation == "ingest" and not params.get("sources") and not params.get("raw_dir"):
        blockers.append(
            {
                "code": "sources_required",
                "message": "ingest needs sources or raw_dir",
                "fix": "pass sources=[...]",
            }
        )
    return blockers


def build_preflight_plan(
    project_id: str,
    operation: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = get_project(project_id)
    state = load_project_state(record)
    payload = dict(params or {})
    op = str(operation or "").strip().lower()
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = _unknown_keys(op, payload)
    blockers.extend(_dependencies(op, state, payload))

    output = Path(record.output)
    try:
        license_items = license_blockers(output, state)
    except Exception as exc:  # noqa: BLE001 - advisory
        license_items = []
        warnings.append({"code": "license_check_failed", "message": str(exc)})
    for item in license_items:
        blockers.append(
            {
                "code": "asset_license_unknown",
                "message": f"asset needs review: {item.get('title') or item.get('path')}",
                "fix": "vf_assets(action='approve', asset_ids=[...])",
            }
        )

    try:
        free = shutil.disk_usage(output).free
        if free < 2 * 1024 * 1024 * 1024:
            blockers.append(
                {
                    "code": "insufficient_disk_space",
                    "message": f"only {free / (1024**3):.1f} GB free",
                    "fix": "free at least 2 GB before rendering",
                }
            )
    except OSError as exc:
        warnings.append({"code": "disk_check_failed", "message": str(exc)})

    gpu = compute_status()
    duration = _duration_sec(state)
    local_factor, remote_factor = ESTIMATES.get(op, (1.0, 0.5))
    estimate = {
        "duration_sec": round(duration, 3),
        "local_sec": round(max(1.0, duration * local_factor), 1),
        "remote_sec": round(max(1.0, duration * remote_factor), 1),
        "transport": gpu.get("transport", "auto"),
        "remote_available": bool(gpu.get("available")),
    }
    if not gpu.get("available"):
        warnings.append(
            {
                "code": "windows_gpu_offline",
                "message": "Windows GPU is offline; the job will run on CPU",
                "fix": "start the Windows worker or use local_only explicitly",
            }
        )

    return {
        "ok": not blockers,
        "project_id": record.project_id,
        "operation": op,
        "blockers": blockers,
        "warnings": warnings,
        "estimate": estimate,
        "plan": PLANS.get(op, []),
        "gpu": gpu,
        "compute": _compute_plan(op, gpu, payload),
    }


__all__ = [
    "DECUPAGE_STAGES",
    "KNOWN_FIELDS",
    "OP_STAGES",
    "SCENE_STAGES",
    "SHORTS_STAGES",
    "build_preflight_plan",
]
