"""Timeline construction step."""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.timeline_builder import build_timeline
from videoflow.application.vad import pad_spans
from videoflow.core.context import PipelineContext
from videoflow.domain.config import JlCutsConfig, ZoomsConfig
from videoflow.domain.state import ProjectState, SampleSpan
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload, require_media
from videoflow.steps.registry import register_step


class TimelineParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable_j_cuts: bool = True
    enable_l_cuts: bool = False
    offset_ms: int = Field(default=200, ge=100, le=500)
    audio_crossfade_ms: int = Field(default=20, ge=10, le=50)
    fade_in_ms: int = Field(default=20, ge=0, le=1000)
    fade_out_ms: int = Field(default=20, ge=0, le=1000)
    fade_curve: Literal["linear", "logarithmic"] = "logarithmic"
    handle_check: bool = True

    zoom_mode: Literal["alternate_cuts", "topic_change", "manual_rules"] = "alternate_cuts"
    zoom_min_scale: float = Field(default=1.0, ge=1.0, le=4.0)
    zoom_max_scale: float = Field(default=1.5, ge=1.0, le=4.0)
    punch_in_scale: float = Field(default=1.15, ge=1.0, le=4.0)
    anchor_point: Literal["center", "upper_third", "face_detect"] = "upper_third"
    progressive_zoom: bool = False
    pan_direction: Literal["none", "left_to_right", "right_to_left"] = "none"

    pad_before_ms: int | None = Field(default=None, ge=0)
    pad_after_ms: int | None = Field(default=None, ge=0)
    project_id: str | None = None
    revision: int = Field(default=1, ge=1)


@register_step
class TimelineStep(BaseStep):
    type = "edit.timeline"
    title = "Build timeline"
    description = (
        "Turn kept speech spans into frame-quantised video and sample-aligned audio segments."
    )
    requires = ("audio.vad",)
    produces = ("timeline",)
    params_model = TimelineParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = TimelineParams.model_validate(params)
        media = require_media(context)
        pad_before = (
            options.pad_before_ms
            if options.pad_before_ms is not None
            else int(context.metadata.get("speech_pad_before_ms", 120))
        )
        pad_after = (
            options.pad_after_ms
            if options.pad_after_ms is not None
            else int(context.metadata.get("speech_pad_after_ms", 150))
        )
        speech = pad_spans(
            context.speech_intervals,
            media.audio_sample_rate,
            pad_before,
            pad_after,
            context.duration_samples(),
        )
        jl = JlCutsConfig(
            enable_j_cuts=options.enable_j_cuts,
            enable_l_cuts=options.enable_l_cuts,
            offset_ms=options.offset_ms,
            audio_crossfade_ms=options.audio_crossfade_ms,
            fade_in_ms=options.fade_in_ms,
            fade_out_ms=options.fade_out_ms,
            fade_curve=options.fade_curve,
            handle_check=options.handle_check,
        )
        zooms = ZoomsConfig(
            mode=options.zoom_mode,
            min_scale=options.zoom_min_scale,
            max_scale=options.zoom_max_scale,
            punch_in_scale=options.punch_in_scale,
            anchor_point=options.anchor_point,
            progressive_zoom=options.progressive_zoom,
            pan_direction=options.pan_direction,
        )
        io.report(20, "Building the cut timeline")
        built = build_timeline(media, speech, jl=jl, zooms=zooms)
        project_id = UUID(options.project_id) if options.project_id else uuid4()
        context.state = ProjectState(
            project_id=project_id,
            revision=options.revision,
            media_info=media,
            vad_intervals=[
                SampleSpan(start_sample=start, end_sample=end) for start, end in speech
            ],
            transcript=list(context.transcript),
            retake_culls=list(context.discard_sentence_ids),
            retake_guard_restores=list(context.restored_sentence_ids),
            manual_overrides=list(context.manual_overrides),
            video_segments=list(built.video_segments),
            audio_segments=list(built.audio_segments),
        )
        context.speech_intervals = speech
        context.warnings.extend(built.warnings)
        context.hashes["timeline"] = digest_payload(
            {
                "spans": speech,
                "video": len(built.video_segments),
                "audio": len(built.audio_segments),
                "jl": jl.model_dump(),
                "zooms": zooms.model_dump(),
            }
        )
        io.report(100, f"{len(built.video_segments)} cuts ready")
