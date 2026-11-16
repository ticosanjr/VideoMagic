"""Plan and apply multicam angle cuts on a multi-source timeline."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.errors import StateNotReadyError
from videoflow.domain.state import MulticamCut, MulticamPlan, ProjectState, VideoSegment
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class MulticamPlanParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["manual", "speech", "alternate"] = "manual"
    primary_source_id: str = ""
    secondary_source_id: str = ""
    segment_sec: float = Field(default=4.0, ge=0.5, le=60.0)
    cuts: list[dict[str, object]] = Field(default_factory=list)
    apply: bool = False


class MulticamApplyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cuts: list[dict[str, object]] = Field(default_factory=list)
    primary_source_id: str = ""


def _timeline_frames(state: ProjectState) -> int:
    return max((clip.timeline_out_frame for clip in state.video_segments), default=0)


def _cut_list(
    context: PipelineContext, state: ProjectState, options: MulticamPlanParams
) -> list[MulticamCut]:
    source_ids = list(state.sources)
    primary = options.primary_source_id or state.primary_source_id or source_ids[0]
    secondary = options.secondary_source_id or next(
        (item for item in source_ids if item != primary), primary
    )
    duration = _timeline_frames(state)
    if duration <= 0:
        return []
    cuts: list[MulticamCut] = []
    if options.mode == "manual" or options.cuts:
        for item in options.cuts:
            try:
                cuts.append(
                    MulticamCut(
                        start_frame=int(item.get("start_frame") or 0),
                        end_frame=int(item.get("end_frame") or 0),
                        source_id=str(item.get("source_id") or primary),
                    )
                )
            except (TypeError, ValueError):
                continue
    elif options.mode == "alternate":
        step = max(
            1,
            round(
                options.segment_sec * (context.media.fps_num / context.media.fps_den)
                if context.media
                else 30
            ),
        )
        cursor = 0
        index = 0
        while cursor < duration:
            end = min(duration, cursor + step)
            cuts.append(
                MulticamCut(
                    start_frame=cursor,
                    end_frame=end,
                    source_id=primary if index % 2 == 0 else secondary,
                )
            )
            cursor = end
            index += 1
    else:
        rate = context.media.audio_sample_rate if context.media else 48000
        fps = context.media.fps_num / context.media.fps_den if context.media else 30.0
        for sentence in context.transcript:
            start = max(0, round(sentence.start_sample / rate * fps))
            end = min(duration, round(sentence.end_sample / rate * fps))
            if end <= start:
                continue
            cuts.append(
                MulticamCut(
                    start_frame=start,
                    end_frame=end,
                    source_id=secondary if sentence.speaker else primary,
                )
            )
    cuts.sort(key=lambda item: (item.start_frame, item.end_frame))
    merged: list[MulticamCut] = []
    for cut in cuts:
        if cut.end_frame <= 0 or cut.start_frame >= duration:
            continue
        clamped = cut.model_copy(
            update={
                "start_frame": max(0, cut.start_frame),
                "end_frame": min(duration, cut.end_frame),
            }
        )
        if (
            merged
            and merged[-1].source_id == clamped.source_id
            and clamped.start_frame <= merged[-1].end_frame
        ):
            previous = merged[-1]
            merged[-1] = previous.model_copy(
                update={"end_frame": max(previous.end_frame, clamped.end_frame)}
            )
        else:
            merged.append(clamped)
    if not merged:
        merged = [MulticamCut(start_frame=0, end_frame=duration, source_id=primary)]
    if merged[0].start_frame > 0:
        merged.insert(
            0,
            MulticamCut(start_frame=0, end_frame=merged[0].start_frame, source_id=primary),
        )
    if merged[-1].end_frame < duration:
        merged.append(
            MulticamCut(
                start_frame=merged[-1].end_frame,
                end_frame=duration,
                source_id=primary,
            )
        )
    return merged


def _apply_plan(
    context: PipelineContext, state: ProjectState, plan: MulticamPlan
) -> list[VideoSegment]:
    if context.media is None:
        raise StateNotReadyError("Multicam apply requires media info")
    fps = context.media.fps_num / context.media.fps_den
    rate = context.media.audio_sample_rate
    segments: list[VideoSegment] = []
    cursor = 0
    for cut in plan.cuts:
        if cut.end_frame <= cut.start_frame:
            continue
        media = state.source_media(cut.source_id)
        if media is None:
            continue
        offset_samples = state.source_offsets.get(cut.source_id, 0)
        offset_frames = round(offset_samples / rate * fps)
        source_in = max(0, cut.start_frame + offset_frames)
        source_out = min(media.duration_frames, cut.end_frame + offset_frames)
        if source_out <= source_in:
            continue
        duration = source_out - source_in
        segments.append(
            VideoSegment(
                clip_id=f"mc-{len(segments) + 1:04d}",
                source_id=cut.source_id,
                source_in_frame=source_in,
                source_out_frame=source_out,
                timeline_in_frame=cursor,
                timeline_out_frame=cursor + duration,
            )
        )
        cursor += duration
    if not segments:
        raise StateNotReadyError("Multicam plan produced no segments")
    return segments


@register_step
class MulticamPlanStep(BaseStep):
    type = "multicam.plan"
    title = "Plan multicam angles"
    description = "Build manual, speaker, or alternating angle cuts for a multi-source timeline."
    produces = ("multicam_plan", "timeline")
    params_model = MulticamPlanParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = MulticamPlanParams.model_validate(params)
        state = context.state
        if state is None:
            raise StateNotReadyError("Multicam plan requires a timeline")
        cuts = _cut_list(context, state, options)
        plan = MulticamPlan(cuts=cuts, mode=options.mode)
        updated = state.model_copy(update={"multicam": plan})
        if options.apply:
            updated = updated.model_copy(
                update={"video_segments": _apply_plan(context, updated, plan)}
            )
        context.state = updated
        context.metadata["multicam_plan"] = plan.model_dump(mode="json")
        target = context.work / "multicam_plan.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(plan.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
        )
        context.artifacts["multicam_plan"] = str(target)
        context.hashes["multicam.plan"] = digest_payload(plan.model_dump(mode="json"))
        io.report(100, f"{len(cuts)} multicam cut(s) planned")


@register_step
class MulticamApplyStep(BaseStep):
    type = "multicam.apply"
    title = "Apply multicam angles"
    description = "Apply a saved multicam plan to the video segments."
    produces = ("timeline",)
    params_model = MulticamApplyParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = MulticamApplyParams.model_validate(params)
        state = context.state
        if state is None:
            raise StateNotReadyError("Multicam apply requires a timeline")
        if options.cuts:
            cuts = [
                MulticamCut(
                    start_frame=int(item.get("start_frame") or 0),
                    end_frame=int(item.get("end_frame") or 0),
                    source_id=str(item.get("source_id") or state.primary_source_id),
                )
                for item in options.cuts
            ]
            plan = MulticamPlan(cuts=cuts, mode="manual")
        elif state.multicam is not None:
            plan = state.multicam
        else:
            raise StateNotReadyError("Multicam apply has no plan")
        updated = state.model_copy(
            update={
                "video_segments": _apply_plan(context, state, plan),
                "multicam": plan,
            }
        )
        context.state = updated
        context.hashes["multicam.apply"] = digest_payload(plan.model_dump(mode="json"))
        io.report(100, f"Applied {len(plan.cuts)} multicam cut(s)")
