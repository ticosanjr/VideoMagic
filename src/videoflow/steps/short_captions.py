"""Generate per-layout ASS captions, SFX cues, and Short ending."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.scene_intel.io import read_json, write_json
from videoflow.application.short_composition.captions import (
    DEFAULT_FONT_SIZE,
    DEFAULT_MAX_CHARS,
    DEFAULT_MAX_GAP,
    DEFAULT_MAX_LINES,
    DEFAULT_MAX_WORDS,
    DEFAULT_MIN_WORDS,
    DEFAULT_OUTLINE,
    DEFAULT_SHADOW,
    assign_layouts,
    build_short_ass,
    group_words,
    proportional_words,
    sanitize_blocks,
    words_from_sentences,
)
from videoflow.application.short_composition.geometry import subtitle_y_map
from videoflow.application.short_composition.rhythm import (
    end_settings,
    layout_sfx_cues,
    snap_boundaries,
)
from videoflow.application.short_composition.validate import validate_plan
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ShortPlanError, StateNotReadyError
from videoflow.domain.scenes import ScenesManifest
from videoflow.domain.short_composition import ShortCompositionPlan
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class ShortCaptionsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_path: str = ""
    font_family: str = "Arial"
    font_size: int = Field(default=DEFAULT_FONT_SIZE, ge=32, le=120)
    primary_color: str = "#FFFFFF"
    highlight_color: str = "#FFD400"
    outline_color: str = "#000000"
    outline_width: int = Field(default=DEFAULT_OUTLINE, ge=0, le=12)
    shadow: int = Field(default=DEFAULT_SHADOW, ge=0, le=12)
    uppercase: bool = False
    max_words: int = Field(default=DEFAULT_MAX_WORDS, ge=1, le=8)
    min_words: int = Field(default=DEFAULT_MIN_WORDS, ge=1, le=8)
    max_chars: int = Field(default=DEFAULT_MAX_CHARS, ge=8, le=40)
    max_lines: int = Field(default=DEFAULT_MAX_LINES, ge=1, le=4)
    max_gap: float = Field(default=DEFAULT_MAX_GAP, ge=0.0, le=3.0)
    snap_tolerance_sec: float = Field(default=0.3, ge=0.0, le=1.0)
    min_segment_sec: float = Field(default=2.5, ge=1.0, le=10.0)
    sfx_enabled: bool = True
    sfx_asset: str = "whoosh_soft.wav"
    sfx_db: float = Field(default=-18.0, ge=-60.0, le=0.0)
    rms_profile_path: str = ""
    next_speech_sec: float = Field(default=0.0, ge=0.0)
    pad_ms: int = Field(default=350, ge=0, le=2000)
    fade_ms: int = Field(default=80, ge=0, le=1000)
    strict: bool = True


def _plan(context: PipelineContext, override: str) -> ShortCompositionPlan:
    raw: dict[str, Any] = {}
    if override:
        raw = read_json(Path(override).expanduser())
    if not raw:
        metadata = context.metadata.get("short_plan")
        if isinstance(metadata, dict):
            raw = metadata
    if not raw:
        artifact = context.artifacts.get("short_plan", "")
        raw = read_json(Path(artifact)) if artifact else {}
    if not raw:
        raise StateNotReadyError("Run short.plan before short.captions")
    try:
        return ShortCompositionPlan.model_validate(raw)
    except ValueError as exc:
        raise ShortPlanError(f"Invalid Short plan: {exc}") from exc


def _manifest(context: PipelineContext) -> ScenesManifest:
    raw = context.metadata.get("scenes_manifest")
    if not isinstance(raw, dict) or not raw:
        artifact = context.artifacts.get("scenes_manifest", "")
        raw = read_json(Path(artifact)) if artifact else {}
    if not raw:
        raise StateNotReadyError("Run scene.analyze before short.captions")
    try:
        return ScenesManifest.model_validate(raw)
    except ValueError as exc:
        raise ShortPlanError(f"Invalid scene manifest: {exc}") from exc


def _supercontext(context: PipelineContext) -> dict[str, Any]:
    raw = context.metadata.get("scenes_supercontext")
    if isinstance(raw, dict) and raw:
        return raw
    artifact = context.artifacts.get("scenes_supercontext", "")
    return read_json(Path(artifact)) if artifact else {}


def _asu_words(
    supercontext: dict[str, Any],
    *,
    start_sec: float,
    end_sec: float,
) -> list[Any]:
    words = []
    for asu in supercontext.get("asus", []):
        if not isinstance(asu, dict):
            continue
        try:
            start = float(asu.get("start_sec", 0.0))
            end = float(asu.get("end_sec", 0.0))
        except (TypeError, ValueError):
            continue
        if end <= start_sec or start >= end_sec:
            continue
        words.extend(
            proportional_words(
                str(asu.get("text") or ""),
                start=max(0.0, start - start_sec),
                end=min(end_sec, end) - start_sec,
            )
        )
    return words


def _rms_valleys(
    profile: dict[str, Any],
    *,
    target_abs_sec: float,
    plan_start: float,
    window_sec: float = 0.15,
) -> list[float]:
    values = profile.get("db")
    if not isinstance(values, list) or len(values) < 3:
        return []
    rate = max(1, int(profile.get("sample_rate") or 48_000))
    hop = max(1, int(profile.get("hop_samples") or 1))
    first = max(1, int((target_abs_sec - window_sec) * rate / hop))
    last = min(len(values) - 2, int((target_abs_sec + window_sec) * rate / hop) + 1)
    valleys: list[float] = []
    for index in range(first, last + 1):
        value = float(values[index])
        if value <= float(values[index - 1]) and value <= float(values[index + 1]):
            valleys.append(round(index * hop / rate - plan_start, 6))
    return valleys


def _next_speech(context: PipelineContext, *, after_sec: float) -> float | None:
    rate = 0
    if context.media is not None:
        rate = context.media.audio_sample_rate
    rate = max(1, rate or 48_000)
    candidates = [
        start / rate
        for start, _end in context.speech_intervals
        if start / rate > after_sec + 0.02
    ]
    return min(candidates) if candidates else None


@register_step
class ShortCaptionsStep(BaseStep):
    type = "short.captions"
    title = "Short captions and rhythm"
    description = (
        "Snap layout cuts to caption/ASU boundaries, build 3-4 word ASS blocks, "
        "sanitize overlaps, add SFX cues, and compute padding/fade."
    )
    status = "available"
    icon = "CC"
    color = "#f59e0b"
    requires = ("short.plan",)
    produces = ("short_captions", "short_cues")
    params_model = ShortCaptionsParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ShortCaptionsParams.model_validate(params)
        plan = _plan(context, options.plan_path)
        manifest = _manifest(context)
        supercontext = _supercontext(context)
        rate = (
            context.media.audio_sample_rate if context.media is not None else 48_000
        )
        start_abs = plan.start
        end_abs = plan.end
        words = words_from_sentences(
            context.transcript,
            sample_rate=rate,
            start_sec=start_abs,
            end_sec=end_abs,
        )
        warnings: list[str] = []
        if not words:
            words = _asu_words(supercontext, start_sec=start_abs, end_sec=end_abs)
            if words:
                warnings.append("CAPTIONS_FROM_ASU_PROPORTIONAL_TIMING")
        if not words:
            raise StateNotReadyError(
                "No transcript words or ASUs are available for captions"
            )
        asu_boundaries = []
        for asu in supercontext.get("asus", []):
            if not isinstance(asu, dict):
                continue
            try:
                asu_boundaries.append(float(asu.get("start_sec", 0.0)) - plan.start)
            except (TypeError, ValueError):
                continue
        plan, snap_warnings = snap_boundaries(
            plan,
            [word.start for word in words if word.start > 0] + asu_boundaries,
            tolerance=options.snap_tolerance_sec,
            min_duration=options.min_segment_sec,
        )
        warnings.extend(snap_warnings)
        blocks, group_warnings = group_words(
            words,
            layout_boundaries=[segment.rel_start for segment in plan.segments[1:]],
            max_words=options.max_words,
            min_words=options.min_words,
            max_chars=options.max_chars,
            max_lines=options.max_lines,
            max_gap=options.max_gap,
        )
        warnings.extend(group_warnings)
        blocks, layout_warnings = assign_layouts(
            blocks,
            plan,
            subtitle_y=subtitle_y_map(),
        )
        warnings.extend(layout_warnings)
        blocks, sanitize_warnings = sanitize_blocks(blocks)
        warnings.extend(sanitize_warnings)
        validation = validate_plan(plan, manifest)
        if validation["errors"] and options.strict:
            raise ShortPlanError("; ".join(str(item) for item in validation["errors"]))
        warnings.extend(str(item) for item in validation["warnings"])
        ass_path = Path(context.output) / "shorts" / plan.short_id / "captions.ass"
        ass_path.parent.mkdir(parents=True, exist_ok=True)
        ass_path.write_text(
            build_short_ass(
                blocks,
                font_family=options.font_family,
                font_size=options.font_size,
                primary_color=options.primary_color,
                highlight_color=options.highlight_color,
                outline_color=options.outline_color,
                outline_width=options.outline_width,
                shadow=options.shadow,
                uppercase=options.uppercase,
            ),
            encoding="utf-8",
        )
        profile: dict[str, Any] = {}
        profile_path = options.rms_profile_path
        if not profile_path:
            raw_profile = context.metadata.get("vad_rms")
            if isinstance(raw_profile, dict):
                profile_path = str(raw_profile.get("path") or "")
        if profile_path:
            profile = read_json(Path(profile_path))
        content_end_abs = plan.start + plan.duration_sec
        next_speech = options.next_speech_sec or _next_speech(
            context, after_sec=content_end_abs
        )
        ending = end_settings(
            plan,
            rms_valleys=_rms_valleys(
                profile,
                target_abs_sec=content_end_abs,
                plan_start=plan.start,
            ),
            next_speech_sec=next_speech,
            pad_ms=options.pad_ms,
            fade_ms=options.fade_ms,
        )
        sfx = layout_sfx_cues(
            plan,
            enabled=options.sfx_enabled,
            asset=options.sfx_asset,
            volume_db=options.sfx_db,
        )
        cues = {
            "schema_version": 1,
            "short_id": plan.short_id,
            "ass_path": str(ass_path),
            "caption_count": len(blocks),
            "captions": [
                {
                    "start": block.start,
                    "end": block.end,
                    "text": block.text,
                    "lines": list(block.lines),
                    "layout": block.layout,
                    "subtitle_y": block.subtitle_y,
                }
                for block in blocks
            ],
            "sfx": sfx,
            "ending": ending,
            "warnings": warnings,
            "validation": validation,
        }
        cues_path = ass_path.with_name("short_cues.json")
        write_json(cues_path, cues)
        plan_path = Path(context.artifacts.get("short_plan") or ass_path.with_name(
            "short_composition_plan.json"
        ))
        write_json(plan_path, plan.model_dump(mode="json"))
        context.metadata["short_plan"] = plan.model_dump(mode="json")
        context.hashes["short.plan"] = digest_payload(plan.model_dump(mode="json"))
        context.metadata["short_captions"] = {
            "ass_path": str(ass_path),
            "count": len(blocks),
            "warnings": warnings,
        }
        context.metadata["short_cues"] = cues
        context.artifacts["short_captions"] = str(ass_path)
        context.artifacts["short_cues"] = str(cues_path)
        context.hashes["short.captions"] = digest_payload(cues)
        context.short_captions[plan.short_id] = str(ass_path)
        for warning in warnings:
            if warning not in context.warnings:
                context.warnings.append(warning)
        io.report(
            100,
            f"{len(blocks)} caption block(s), {len(sfx)} SFX cue(s)",
        )


__all__ = ["ShortCaptionsParams", "ShortCaptionsStep"]
