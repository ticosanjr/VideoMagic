"""Timeline construction step."""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from videoflow.application.retakes import subtract_spans
from videoflow.application.timeline_builder import (
    build_inactive_segments,
    build_timeline,
    detect_noise_spans,
    transcript_spans,
)
from videoflow.application.vad import pad_spans
from videoflow.core.context import PipelineContext
from videoflow.domain.config import JlCutsConfig, ZoomsConfig
from videoflow.domain.state import InactiveSpan, ProjectState, SampleSpan
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload, require_media
from videoflow.steps.registry import register_step


class TimelineParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cut_mode: Literal["custom", "hard", "j_cut", "l_cut"] = "custom"
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
    use_transcript_spans: bool = True
    noise_filter: Literal["off", "non_speech", "non_speech_and_nonlexical"] = (
        "non_speech"
    )
    noise_min_ms: int = Field(default=180, ge=0, le=5000)
    noise_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    transition_frames: int = Field(default=0, ge=0, le=120)
    transition_type: Literal["crossfade", "fade_to_black"] = "crossfade"
    project_id: str | None = None
    revision: int = Field(default=1, ge=1)
    replace_manual: bool = True

    @model_validator(mode="after")
    def resolve_cut_mode(self) -> TimelineParams:
        if self.cut_mode == "hard":
            self.enable_j_cuts = False
            self.enable_l_cuts = False
        elif self.cut_mode == "j_cut":
            self.enable_j_cuts = True
            self.enable_l_cuts = False
        elif self.cut_mode == "l_cut":
            self.enable_j_cuts = False
            self.enable_l_cuts = True
        return self


@register_step
class TimelineStep(BaseStep):
    type = "edit.timeline"
    version = "3"
    title = "Build timeline"
    description = (
        "Turn kept speech spans into frame-quantised video and sample-aligned audio segments."
    )
    requires = ("audio.vad",)
    produces = ("timeline", "inactive_spans")
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
        use_transcript = (
            options.use_transcript_spans
            and bool(context.metadata.get("transcript_normalized"))
            and bool(context.transcript)
        )
        if use_transcript:
            speech, noise_spans = transcript_spans(
                context.transcript,
                set(context.discard_sentence_ids),
                sample_rate=media.audio_sample_rate,
                duration_samples=context.duration_samples(),
                pad_before_ms=pad_before,
                pad_after_ms=pad_after,
                noise_mode=options.noise_filter,
                noise_confidence=options.noise_confidence,
            )
            context.metadata["timeline_units"] = "transcript"
        else:
            noise_spans = detect_noise_spans(
                context.speech_intervals,
                context.transcript,
                sample_rate=media.audio_sample_rate,
                mode=options.noise_filter,
                min_ms=options.noise_min_ms,
                confidence=options.noise_confidence,
            )
            raw_speech = context.speech_intervals
            if noise_spans:
                raw_speech = subtract_spans(
                    raw_speech,
                    [(span.start_sample, span.end_sample) for span in noise_spans],
                )
            speech = pad_spans(
                raw_speech,
                media.audio_sample_rate,
                pad_before,
                pad_after,
                context.duration_samples(),
            )
            context.metadata["timeline_units"] = "vad"
        if noise_spans:
            seconds = sum(
                span.end_sample - span.start_sample for span in noise_spans
            ) / media.audio_sample_rate
            context.warnings.append(
                f"Noise filter removed {len(noise_spans)} non-speech span(s) "
                f"({seconds:.1f}s)."
            )
            context.metadata["noise_filter"] = {
                "mode": options.noise_filter,
                "spans": len(noise_spans),
                "seconds": round(seconds, 3),
                "units": context.metadata.get("timeline_units", "vad"),
            }
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
        built = build_timeline(
            media,
            speech,
            jl=jl,
            zooms=zooms,
            transition_frames=options.transition_frames,
            transition_type=options.transition_type,
        )
        inactive = build_inactive_segments(
            media,
            built.video_segments,
            silence_spans=context.silence_spans,
            retake_spans=context.retake_spans,
            noise_spans=noise_spans,
        )
        revision = options.revision
        if options.replace_manual:
            existing = context.output / "project_state.json"
            if existing.is_file():
                try:
                    current = ProjectState.model_validate_json(
                        existing.read_text(encoding="utf-8")
                    )
                except (OSError, ValueError):
                    current = None
                if current is not None and current.revision > revision:
                    revision = current.revision + 1
                    context.warnings.append(
                        "Manual timeline edits at revision "
                        f"{current.revision} were replaced by this recipe build."
                    )
        project_id = UUID(options.project_id) if options.project_id else uuid4()
        context.state = ProjectState(
            project_id=project_id,
            revision=revision,
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
            inactive_segments=list(inactive),
        )
        context.inactive_spans = [
            InactiveSpan(
                start_sample=segment.audio.source_in_sample,
                end_sample=segment.audio.source_out_sample,
                reason=segment.reason,
            )
            for segment in inactive
        ]
        context.speech_intervals = speech
        context.warnings.extend(built.warnings)
        context.hashes["timeline"] = digest_payload(
            {
                "spans": speech,
                "video": len(built.video_segments),
                "audio": len(built.audio_segments),
                "inactive": len(inactive),
                "noise": [span.model_dump() for span in noise_spans],
                "jl": jl.model_dump(),
                "zooms": zooms.model_dump(),
            }
        )
        io.report(100, f"{len(built.video_segments)} cuts ready")
