"""Detect static talking-head stretches and propose pacing interventions."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.headless import PacingCue
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class PacingParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    short_static_sec: float = Field(default=5.0, ge=1.0, le=60.0)
    long_static_sec: float = Field(default=12.0, ge=2.0, le=120.0)
    long_form: bool = False
    inject: str = Field(default="none", pattern="^(none|zoom|layout|broll)$")
    min_gap_sec: float = Field(default=2.0, ge=0.0, le=30.0)


@register_step
class PacingAuditStep(BaseStep):
    type = "pacing.visual_audit"
    status = "available"
    icon = "⏱"
    color = "#eab308"
    title = "Visual pacing audit"
    description = "Find static talking-head stretches and propose zoom, layout, or B-roll."
    requires = ()
    produces = ("pacing_plan",)
    params_model = PacingParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = PacingParams.model_validate(params)
        threshold = options.long_static_sec if options.long_form else options.short_static_sec
        cues: list[PacingCue] = []
        if context.state is None:
            io.report(100, "No timeline state; pacing audit skipped")
            context.metadata["pacing_plan"] = []
            return
        timebase = context.media.timebase() if context.media is not None else None
        if timebase is None:
            context.metadata["pacing_plan"] = []
            io.report(100, "No media timebase; pacing audit skipped")
            return
        for segment in context.state.video_segments:
            start = timebase.frames_to_seconds(segment.timeline_in_frame)
            end = timebase.frames_to_seconds(segment.timeline_out_frame)
            duration = end - start
            if duration <= threshold:
                continue
            if self._has_overlay(context, start, end):
                continue
            cues.append(
                PacingCue(
                    start_sec=round(start, 3),
                    end_sec=round(end, 3),
                    action=options.inject if options.inject != "none" else "zoom",
                    reason=f"static shot for {duration:.1f}s (> {threshold:.1f}s)",
                )
            )
        context.metadata["pacing_plan"] = [cue.model_dump(mode="json") for cue in cues]
        context.artifacts["pacing_plan"] = str(context.work / "pacing_plan.json")
        (context.work / "pacing_plan.json").write_text(
            __import__("json").dumps([cue.model_dump(mode="json") for cue in cues], indent=2)
            + "\n",
            encoding="utf-8",
        )
        io.report(100, f"Pacing audit: {len(cues)} static stretch(es)")

    @staticmethod
    def _has_overlay(context: PipelineContext, start: float, end: float) -> bool:
        if context.state is None or context.media is None:
            return False
        timebase = context.media.timebase()
        for overlay in context.state.overlays:
            o_start = timebase.frames_to_seconds(overlay.start_frame)
            o_end = timebase.frames_to_seconds(overlay.start_frame + overlay.duration_frames)
            if o_start < end and o_end > start:
                return True
        return False
