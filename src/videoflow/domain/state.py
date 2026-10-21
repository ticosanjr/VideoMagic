"""Persisted project state. Authoritative times are integers, never float seconds."""

from __future__ import annotations

from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from videoflow.domain.config import ModuleEnabled, ModulesConfig
from videoflow.domain.constants import SCHEMA_VERSION
from videoflow.domain.timebase import Timebase

OverrideAction = Literal["keep", "discard"]
TransformType = Literal["none", "punch_in", "slow_zoom_in", "slow_zoom_out", "pan"]
FadeCurve = Literal["linear", "logarithmic"]
ReframeMode = Literal["center_crop_9_16", "auto_face_tracking_yolo"]
AnchorPoint = Literal["center", "upper_third", "face_detect"]
PanDirection = Literal["none", "left_to_right", "right_to_left"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MediaInfo(StrictModel):
    source_path: str = Field(min_length=1)
    duration_frames: int = Field(ge=0)
    fps_num: int = Field(gt=0)
    fps_den: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    audio_sample_rate: int = Field(gt=0)
    start_timecode_frames: int = Field(default=0, ge=0)

    def timebase(self) -> Timebase:
        return Timebase(self.fps_num, self.fps_den, self.audio_sample_rate)


class SampleSpan(StrictModel):
    start_sample: int = Field(ge=0)
    end_sample: int = Field(ge=0)

    @model_validator(mode="after")
    def exclusive_end(self) -> Self:
        if self.end_sample <= self.start_sample:
            raise ValueError("end_sample must be greater than start_sample")
        return self


class WordTiming(StrictModel):
    word: str
    start_sample: int = Field(ge=0)
    end_sample: int = Field(ge=0)
    probability: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def exclusive_end(self) -> Self:
        if self.end_sample < self.start_sample:
            raise ValueError("end_sample before start_sample")
        return self


class Sentence(StrictModel):
    id: int = Field(ge=0)
    start_sample: int = Field(ge=0)
    end_sample: int = Field(ge=0)
    text: str
    words: list[WordTiming] = Field(default_factory=list)

    @model_validator(mode="after")
    def exclusive_end(self) -> Self:
        if self.end_sample < self.start_sample:
            raise ValueError("end_sample before start_sample")
        return self


class ManualOverride(StrictModel):
    """A sentence override, or a word override inside that sentence."""

    sentence_id: int = Field(ge=0)
    word_index: int | None = Field(default=None, ge=0)
    action: OverrideAction


class Transform(StrictModel):
    scale: float = Field(default=1.0, ge=1.0, le=4.0)
    pos_x: float = 0.0
    pos_y: float = 0.0
    type: TransformType = "none"
    anchor: AnchorPoint = "upper_third"
    pan_direction: PanDirection = "none"


class VideoSegment(StrictModel):
    clip_id: str = Field(min_length=1)
    source_in_frame: int = Field(ge=0)
    source_out_frame: int = Field(ge=0)
    timeline_in_frame: int = Field(ge=0)
    timeline_out_frame: int = Field(ge=0)
    transform: Transform = Field(default_factory=Transform)

    @model_validator(mode="after")
    def exclusive_ranges(self) -> Self:
        if self.source_out_frame <= self.source_in_frame:
            raise ValueError("video source range must be non-empty")
        if self.timeline_out_frame <= self.timeline_in_frame:
            raise ValueError("video timeline range must be non-empty")
        return self


class AudioSegment(StrictModel):
    clip_id: str = Field(min_length=1)
    source_in_sample: int = Field(ge=0)
    source_out_sample: int = Field(ge=0)
    timeline_in_sample: int = Field(ge=0)
    timeline_out_sample: int = Field(ge=0)
    fade_in_samples: int = Field(default=0, ge=0)
    fade_out_samples: int = Field(default=0, ge=0)
    fade_curve: FadeCurve = "logarithmic"

    @model_validator(mode="after")
    def exclusive_ranges(self) -> Self:
        if self.source_out_sample <= self.source_in_sample:
            raise ValueError("audio source range must be non-empty")
        if self.timeline_out_sample <= self.timeline_in_sample:
            raise ValueError("audio timeline range must be non-empty")
        return self


class VerticalClip(StrictModel):
    clip_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    start_sample: int = Field(ge=0)
    end_sample: int = Field(ge=0)
    crop_focus_x: float = Field(default=0.5, ge=0.0, le=1.0)
    reframe_mode: ReframeMode = "center_crop_9_16"

    @model_validator(mode="after")
    def exclusive_end(self) -> Self:
        if self.end_sample <= self.start_sample:
            raise ValueError("vertical clip range must be non-empty")
        return self


class ProjectState(StrictModel):
    """The single JSON document under ``.videoflow/project_state.json``."""

    schema_version: Literal[1] = SCHEMA_VERSION
    project_id: UUID = Field(default_factory=uuid4)
    revision: int = Field(default=1, ge=1)
    media_info: MediaInfo | None = None
    modules_config: ModulesConfig = Field(default_factory=ModulesConfig)
    module_enabled: ModuleEnabled = Field(default_factory=ModuleEnabled)
    cache_hashes: dict[str, str] = Field(default_factory=dict)
    vad_intervals: list[SampleSpan] = Field(default_factory=list)
    transcript: list[Sentence] = Field(default_factory=list)
    retake_culls: list[int] = Field(default_factory=list)
    retake_guard_restores: list[int] = Field(default_factory=list)
    manual_overrides: list[ManualOverride] = Field(default_factory=list)
    video_segments: list[VideoSegment] = Field(default_factory=list)
    audio_segments: list[AudioSegment] = Field(default_factory=list)
    vertical_clips: list[VerticalClip] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_sentence_ids(self) -> Self:
        ids = [sentence.id for sentence in self.transcript]
        if len(ids) != len(set(ids)):
            raise ValueError("transcript sentence ids must be unique")
        return self


class LlmRetakeResponse(StrictModel):
    """The only payload the retake model is allowed to return."""

    discard_sentence_ids: list[int] = Field(default_factory=list)
    reasoning: str = Field(min_length=1)


class ShortsProposalClip(StrictModel):
    title: str = Field(min_length=1)
    sentence_ids: list[int] = Field(min_length=1)


class LlmShortsResponse(StrictModel):
    """The only payload the shorts model is allowed to return."""

    clips: list[ShortsProposalClip] = Field(default_factory=list)
    reasoning: str = Field(min_length=1)


class ApiError(StrictModel):
    ok: Literal[False] = False
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, str] = Field(default_factory=dict)


class JobRecord(StrictModel):
    job_id: UUID
    project_id: UUID
    status: Literal["queued", "running", "cancelled", "succeeded", "failed"]
    active_module: str | None = None
    message: str = ""


class Preset(StrictModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    modules_config: ModulesConfig = Field(default_factory=ModulesConfig)
    module_enabled: ModuleEnabled = Field(default_factory=ModuleEnabled)
