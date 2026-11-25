"""Acoustic snap plan and non-destructive timeline application."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.decupage.deterministic import build_safe_speech_spans
from videoflow.application.decupage.snap import build_plan, report_markdown
from videoflow.application.timeline_builder import (
    build_inactive_segments,
    build_timeline,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.config import JlCutsConfig, ZoomsConfig
from videoflow.domain.decupage import DecupagePlan
from videoflow.domain.errors import StateNotReadyError, TimelineConflict
from videoflow.domain.state import InactiveSpan, ProjectState, SampleSpan
from videoflow.domain.timebase import Rounding
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload, require_media
from videoflow.steps.decupage_review import _asus
from videoflow.steps.registry import register_step


class SnapParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pre_roll_ms: float = Field(default=75.0, ge=0.0, le=500.0)
    post_roll_ms: float = Field(default=115.0, ge=0.0, le=500.0)
    start_search_left_ms: float = Field(default=100.0, ge=0.0, le=500.0)
    start_search_right_ms: float = Field(default=20.0, ge=0.0, le=200.0)
    end_search_left_ms: float = Field(default=20.0, ge=0.0, le=200.0)
    end_search_right_ms: float = Field(default=130.0, ge=0.0, le=500.0)
    min_cut_gap_ms: float = Field(default=140.0, ge=0.0, le=1000.0)
    crossfade_ms: float = Field(default=18.0, ge=10.0, le=50.0)
    min_clip_ms: float = Field(default=120.0, ge=1.0, le=2000.0)
    pre_roll_floor_ms: float = Field(default=75.0, ge=0.0, le=500.0)
    post_roll_floor_ms: float = Field(default=115.0, ge=0.0, le=500.0)
    pacing_profile: str = "tight"
    qa_dead_air_ms: int = Field(default=650, ge=0, le=5000)


def _overlap_samples(
    spans: list[tuple[int, int]],
    cuts: list[tuple[int, int]],
) -> int:
    total = 0
    for start, end in spans:
        for cut_start, cut_end in cuts:
            low = max(start, cut_start)
            high = min(end, cut_end)
            if high > low:
                total += high - low
    return total


def _profile(context: PipelineContext) -> dict[str, Any]:
    raw = context.metadata.get("vad_rms")
    if isinstance(raw, dict) and raw.get("path"):
        try:
            return json.loads(Path(str(raw["path"])).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return {}


@register_step
class DecupageSnapStep(BaseStep):
    type = "decupage.snap"
    title = "Decupage snap"
    description = "Snap active ASUs to RMS valleys, pad, merge micro-cuts, and quantise frames."
    requires = ("speech.asu",)
    produces = ("decupage_plan", "decupage_report")
    params_model = SnapParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = SnapParams.model_validate(params)
        media = require_media(context)
        asus = _asus(context)
        cuts = context.metadata.get("decupage_cuts", [])
        events = context.metadata.get("audio_events", [])
        flags = context.metadata.get("decupage_review_flags", [])
        profile = _profile(context)
        timebase = media.timebase()
        duration_samples = timebase.seconds_to_samples(
            timebase.frames_to_seconds(media.duration_frames),
            Rounding.NEAREST,
        )
        safe_spans, flagged_long_cuts = build_safe_speech_spans(
            list(context.speech_intervals),
            list(context.transcript),
            set(context.discard_sentence_ids),
            sample_rate=media.audio_sample_rate,
            duration_samples=duration_samples,
            rms_profile=profile,
        )
        context.metadata["decupage_safe_spans"] = [list(item) for item in safe_spans]
        context.metadata["flagged_long_cuts"] = flagged_long_cuts
        context.metadata["pacing_profile"] = options.pacing_profile
        context.metadata["qa_dead_air_ms"] = options.qa_dead_air_ms
        plan = build_plan(
            media,
            asus,
            list(cuts) if isinstance(cuts, list) else [],
            profile=profile,
            base_spans=safe_spans or None,
            flagged_long_cuts=flagged_long_cuts,
            noise_events=list(events) if isinstance(events, list) else [],
            review_flags=list(flags) if isinstance(flags, list) else [],
            pre_roll_ms=options.pre_roll_ms,
            post_roll_ms=options.post_roll_ms,
            start_search_left_ms=options.start_search_left_ms,
            start_search_right_ms=options.start_search_right_ms,
            end_search_left_ms=options.end_search_left_ms,
            end_search_right_ms=options.end_search_right_ms,
            min_cut_gap_ms=options.min_cut_gap_ms,
            crossfade_ms=options.crossfade_ms,
            min_clip_ms=options.min_clip_ms,
            pre_roll_floor_ms=options.pre_roll_floor_ms,
            post_roll_floor_ms=options.post_roll_floor_ms,
        )
        target = context.work / "decupage" / "plan.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(plan.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report = context.work / "decupage" / "report.md"
        report.write_text(report_markdown(plan), encoding="utf-8")
        report_json = context.work / "decupage" / "report.json"
        report_json.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "safe_spans": [list(item) for item in safe_spans],
                    "flagged_long_cuts": flagged_long_cuts,
                    "metrics": plan.metrics,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        context.metadata["decupage_plan"] = plan.model_dump(mode="json")
        context.artifacts["decupage_plan"] = str(target)
        context.artifacts["decupage_report"] = str(report)
        context.artifacts["decupage_report_json"] = str(report_json)
        context.hashes["decupage.safe_spans"] = digest_payload(
            {
                "safe_spans": [list(item) for item in safe_spans],
                "flagged_long_cuts": flagged_long_cuts,
            }
        )
        context.hashes["decupage.snap"] = digest_payload(plan.model_dump(mode="json"))
        io.report(
            100,
            f"{len(plan.active_spans)} active span(s), "
            f"{plan.metrics.get('reduction_pct', 0)}% reduction",
        )


class DecupageTimelineParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int | None = Field(default=None, ge=1)
    replace_manual: bool = True
    audio_crossfade_ms: int = Field(default=18, ge=10, le=50)
    fade_in_ms: int = Field(default=18, ge=0, le=1000)
    fade_out_ms: int = Field(default=18, ge=0, le=1000)
    write_quarantine_markers: bool = True


@register_step
class DecupageTimelineStep(BaseStep):
    type = "decupage.timeline"
    title = "Apply decupage timeline"
    description = "Build the canonical timeline from the snapped decupage plan."
    requires = ("decupage.snap",)
    produces = ("timeline", "decupage_timeline")
    params_model = DecupageTimelineParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = DecupageTimelineParams.model_validate(params)
        media = require_media(context)
        raw = context.metadata.get("decupage_plan")
        if not isinstance(raw, dict) or not raw.get("active_spans"):
            raise StateNotReadyError("Run decupage.snap before decupage.timeline")
        try:
            plan = DecupagePlan.model_validate(raw)
        except (TypeError, ValueError) as exc:
            raise StateNotReadyError(f"Invalid decupage plan: {exc}") from exc
        current = context.state
        if (
            options.expected_revision is not None
            and current is not None
            and current.revision != options.expected_revision
            and not options.replace_manual
        ):
            raise TimelineConflict(
                f"Timeline revision is {current.revision}, expected "
                f"{options.expected_revision}"
            )
        spans = [(item.start_sample, item.end_sample) for item in plan.active_spans]
        cut_spans = [(item.start_sample, item.end_sample) for item in plan.cuts]
        leaked_samples = _overlap_samples(spans, cut_spans)
        leaked = leaked_samples / max(1, plan.sample_rate)
        context.metadata["decupage_cut_leak"] = {
            "seconds": round(leaked, 3),
            "cuts": len(cut_spans),
        }
        if cut_spans and leaked > 0.05:
            context.warnings.append(
                f"{leaked:.2f}s of removed speech survived in the decupage plan."
            )
        jl = JlCutsConfig(
            enable_j_cuts=False,
            enable_l_cuts=False,
            audio_crossfade_ms=options.audio_crossfade_ms,
            fade_in_ms=options.fade_in_ms,
            fade_out_ms=options.fade_out_ms,
        )
        zooms = ZoomsConfig(
            mode="manual_rules",
            min_scale=1.0,
            max_scale=1.0,
            punch_in_scale=1.0,
        )
        built = build_timeline(
            media,
            spans,
            jl=jl,
            zooms=zooms,
            final_tail_guard_ms=0,
        )
        silence: list[InactiveSpan] = []
        retake: list[InactiveSpan] = []
        noise: list[InactiveSpan] = []
        for cut in plan.cuts:
            reason = cut.reason.casefold()
            span = InactiveSpan(
                start_sample=cut.start_sample,
                end_sample=cut.end_sample,
                reason="noise" if "noise" in reason else "retake",
            )
            (noise if span.reason == "noise" else retake).append(span)
        inactive = build_inactive_segments(
            media,
            built.video_segments,
            silence_spans=silence,
            retake_spans=retake,
            noise_spans=noise,
        )
        from uuid import uuid4

        base = current or ProjectState(project_id=uuid4())
        updated = base.model_copy(
            update={
                "media_info": media,
                "vad_intervals": [
                    SampleSpan(start_sample=start, end_sample=end)
                    for start, end in spans
                ],
                "transcript": list(context.transcript),
                "retake_culls": list(context.discard_sentence_ids),
                "manual_overrides": list(context.manual_overrides),
                "video_segments": list(built.video_segments),
                "audio_segments": list(built.audio_segments),
                "inactive_segments": list(inactive),
            }
        )
        context.state = updated
        context.inactive_spans = [
            InactiveSpan(
                start_sample=segment.audio.source_in_sample,
                end_sample=segment.audio.source_out_sample,
                reason=segment.reason,
            )
            for segment in inactive
        ]
        payload = {
            "video_segments": len(updated.video_segments),
            "audio_segments": len(updated.audio_segments),
            "inactive_segments": len(updated.inactive_segments),
            "duration_frames": sum(
                segment.timeline_out_frame - segment.timeline_in_frame
                for segment in updated.video_segments
            ),
            "revision": updated.revision,
            "warnings": list(built.warnings),
            "cut_leak": context.metadata["decupage_cut_leak"],
        }
        target = context.work / "decupage" / "timeline.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        quarantine = _quarantine(plan)
        quarantine_path = context.work / "decupage" / "quarantine.json"
        quarantine_path.write_text(
            json.dumps(quarantine, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        context.metadata["decupage_quarantine"] = quarantine
        context.artifacts["decupage_quarantine"] = str(quarantine_path)
        if options.write_quarantine_markers:
            _write_markers(context, plan, quarantine)
        context.metadata["decupage_timeline"] = payload
        context.artifacts["decupage_timeline"] = str(target)
        context.hashes["decupage.timeline"] = digest_payload(payload)
        context.warnings.extend(built.warnings)
        io.report(
            100,
            f"{payload['video_segments']} video segment(s), "
            f"{payload['inactive_segments']} inactive",
        )


def _quarantine(plan: DecupagePlan) -> list[dict[str, Any]]:
    active = plan.active_spans
    result: list[dict[str, Any]] = []
    colors = {
        "retake": "#FF0000",
        "noise": "#FFA500",
        "silence": "#FFFF00",
        "review": "#FFFF00",
    }
    for index, cut in enumerate(plan.cuts, start=1):
        before = sum(
            min(max(cut.start_sample - span.start_sample, 0), span.end_sample - span.start_sample)
            for span in active
            if span.start_sample < cut.start_sample
        )
        reason = cut.reason.casefold()
        category = "noise" if "noise" in reason else "retake"
        result.append(
            {
                "id": f"decupage-cut-{index:04d}",
                "source_start_sec": round(cut.start_sample / plan.sample_rate, 3),
                "source_end_sec": round(cut.end_sample / plan.sample_rate, 3),
                "timeline_sec": round(before / plan.sample_rate, 3),
                "reason": cut.reason,
                "asu_id": cut.asu_id,
                "needs_broll_or_punch_in": cut.needs_broll_or_punch_in,
                "marker_color": colors.get(category, "#FF0000"),
            }
        )
    return result


def _write_markers(
    context: PipelineContext,
    plan: DecupagePlan,
    quarantine: list[dict[str, Any]],
) -> None:
    from videoflow.application.timeline_meta import add_marker

    for item in quarantine:
        add_marker(
            context.output,
            marker_id=str(item["id"]),
            time_sec=float(item["timeline_sec"]),
            end_sec=float(item["timeline_sec"]),
            label=(
                f"Decupage {item['reason']} "
                f"[{item['source_start_sec']:.3f}-{item['source_end_sec']:.3f}s]"
            ),
            color=str(item["marker_color"]),
        )
    context.artifacts["timeline_meta"] = str(context.output / "timeline_meta.json")
