"""Validate and compile Markdown style metadata into pipeline parameters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from videoflow.application.beatmap_plan import build_beatmap_plan, write_beatmap_plan
from videoflow.application.caption_presets import PRESETS
from videoflow.application.fonts import font_available
from videoflow.application.projects import (
    get_project,
    load_project_state,
    save_project_state,
)
from videoflow.domain.errors import StyleError, StyleNotFoundError
from videoflow.domain.styles import LAYOUT_MODES, MOTION_ENGINES, StyleDefinition

MOTION_ENGINE_ALIASES = {"ffmpeg+hyperframes": "hyperframes"}


def validate_style(style: StyleDefinition) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[str] = []
    if style.caption_preset and style.caption_preset not in PRESETS:
        errors.append(
            {
                "field": "caption_preset",
                "value": style.caption_preset,
                "message": f"unknown caption preset: {style.caption_preset}",
            }
        )
    if style.layout_mode and style.layout_mode not in LAYOUT_MODES:
        errors.append(
            {
                "field": "layout_mode",
                "value": style.layout_mode,
                "message": f"unknown layout mode: {style.layout_mode}",
            }
        )
    if style.motion_engine and style.motion_engine not in MOTION_ENGINES:
        errors.append(
            {
                "field": "motion_engine",
                "value": style.motion_engine,
                "message": f"unknown motion engine: {style.motion_engine}",
            }
        )
    missing_fonts = [name for name in style.fonts if not font_available(name)]
    if missing_fonts:
        errors.append(
            {
                "field": "fonts",
                "value": ", ".join(missing_fonts),
                "message": "fonts are not registered or available through fontconfig",
            }
        )
    if not style.caption_preset:
        warnings.append("style has no caption_preset; captions will use defaults")
    return {
        "ok": not errors,
        "style_id": style.style_id,
        "errors": errors,
        "warnings": warnings,
        "fonts": {"declared": list(style.fonts), "missing": missing_fonts},
        "caption_preset": style.caption_preset,
        "layout_mode": style.layout_mode,
        "motion_engine": style.motion_engine,
    }


def compile_style(style: StyleDefinition) -> dict[str, Any]:
    timeline = {
        "max_silence_ms": style.min_silence_ms,
        "keep_silence_ms": min(300, style.min_silence_ms),
        "project_id": "",
    }
    audio = {"target_lufs": style.target_lufs, "source": "timeline"}
    captions = {"preset": style.caption_preset}
    layout = {"style": style.layout_mode or "auto"}
    motion = {"engine": style.motion_engine or "auto"}
    beatmap = {
        "max_static_sec": style.max_static_sec,
        "min_silence_ms": style.min_silence_ms,
        **dict(style.beatmap_defaults),
    }
    return {
        "style_id": style.style_id,
        "timeline": timeline,
        "audio": audio,
        "captions": captions,
        "layout": layout,
        "motion": motion,
        "beatmap": beatmap,
        "warnings": [],
    }


def apply_style(
    project_id: str,
    style_id: str,
    *,
    generate_beatmap: bool = True,
) -> dict[str, Any]:
    from videoflow.application.style_catalog import StyleCatalog

    try:
        style = StyleCatalog().get(style_id)
    except StyleNotFoundError as exc:
        raise StyleError(str(exc)) from exc
    validation = validate_style(style)
    if not validation["ok"]:
        raise StyleError(
            "Style validation failed: "
            + "; ".join(item["message"] for item in validation["errors"])
        )
    record = get_project(project_id)
    state = load_project_state(record)
    params = compile_style(style)
    params["timeline"]["project_id"] = project_id
    applied = state.model_copy(
        update={
            "style_id": style.style_id,
            "pipeline": state.pipeline.model_copy(
                update={"applied_style_id": style.style_id}
            ),
        }
    )
    work = Path(record.output) / "work"
    work.mkdir(parents=True, exist_ok=True)
    params_path = work / "style_apply.json"
    params_path.write_text(json.dumps(params, indent=2) + "\n", encoding="utf-8")
    plan_path = ""
    plan: dict[str, Any] = {}
    if generate_beatmap:
        plan = build_beatmap_plan(state, style)
        plan_path = str(write_beatmap_plan(Path(record.output), plan))
    saved = save_project_state(
        record,
        applied,
        bump_revision=True,
        snapshot=True,
        snapshot_reason=f"style_apply:{style.style_id}",
        snapshot_step="style.apply",
    )
    return {
        "ok": True,
        "project_id": project_id,
        "style_id": style.style_id,
        "revision": saved.revision,
        "params": params,
        "params_path": str(params_path),
        "beatmap_path": plan_path,
        "timeline_diff": {
            "current_revision": state.revision,
            "new_revision": saved.revision,
            "video_segments": len(state.video_segments),
            "audio_segments": len(state.audio_segments),
            "max_static_sec": style.max_static_sec,
            "min_silence_ms": style.min_silence_ms,
            "layout_mode": style.layout_mode,
            "caption_preset": style.caption_preset,
        },
        "validation": validation,
        "plan": plan,
    }


__all__ = ["apply_style", "compile_style", "validate_style"]
