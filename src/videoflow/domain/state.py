"""Persisted project state. Authoritative times are integers, never float seconds."""

from __future__ import annotations

from typing import Any, Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from videoflow.domain.config import ModuleEnabled, ModulesConfig
from videoflow.domain.constants import SCHEMA_VERSION
from videoflow.domain.timebase import Timebase

OverrideAction = Literal["keep", "discard"]
InactiveReason = Literal["silence", "retake", "manual", "noise"]
TransformType = Literal["none", "punch_in", "slow_zoom_in", "slow_zoom_out", "pan"]
FadeCurve = Literal["linear", "logarithmic"]
ReframeMode = Literal[
    "center_crop_9_16",
    "motion_tracking",
    "face_tracking",
    "auto_face_tracking_yolo",
]
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
    low_confidence: bool = False

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
    speaker: int = Field(default=0, ge=0)
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


class TransformKeyframe(StrictModel):
    at: float = Field(ge=0.0, le=1.0)
    scale: float = Field(ge=1.0, le=4.0)
    pos_x: float = 0.0
    pos_y: float = 0.0
    curve: Literal["linear", "smooth"] = "linear"


class Transform(StrictModel):
    scale: float = Field(default=1.0, ge=1.0, le=4.0)
    pos_x: float = 0.0
    pos_y: float = 0.0
    type: TransformType = "none"
    anchor: AnchorPoint = "upper_third"
    pan_direction: PanDirection = "none"
    keyframes: list[TransformKeyframe] = Field(default_factory=list)


class Transition(StrictModel):
    type: Literal[
        "crossfade",
        "fade_to_black",
        "wipe_left",
        "wipe_right",
        "slide_up",
        "zoom_in",
        "whip_pan",
        "glitch",
    ] = "crossfade"
    duration_frames: int = Field(default=6, ge=1, le=120)
    audio: bool = True


class VideoSegment(StrictModel):
    clip_id: str = Field(min_length=1)
    source_id: str = ""
    source_in_frame: int = Field(ge=0)
    source_out_frame: int = Field(ge=0)
    timeline_in_frame: int = Field(ge=0)
    timeline_out_frame: int = Field(ge=0)
    transform: Transform = Field(default_factory=Transform)
    transition_out: Transition | None = None

    @model_validator(mode="after")
    def exclusive_ranges(self) -> Self:
        if self.source_out_frame <= self.source_in_frame:
            raise ValueError("video source range must be non-empty")
        if self.timeline_out_frame <= self.timeline_in_frame:
            raise ValueError("video timeline range must be non-empty")
        return self


class AudioSegment(StrictModel):
    clip_id: str = Field(min_length=1)
    source_id: str = ""
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


class InactiveSpan(StrictModel):
    """A source-time region that the Recut flow should not play."""

    start_sample: int = Field(ge=0)
    end_sample: int = Field(ge=0)
    reason: InactiveReason = "silence"

    @model_validator(mode="after")
    def exclusive_end(self) -> Self:
        if self.end_sample <= self.start_sample:
            raise ValueError("inactive span must be non-empty")
        return self


class InactiveSegment(StrictModel):
    """A non-destructive removed clip kept for the Recut view."""

    clip_id: str = Field(min_length=1)
    video: VideoSegment
    audio: AudioSegment
    reason: InactiveReason = "manual"


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


OverlayAnchor = Literal[
    "top_left",
    "top_center",
    "top_right",
    "bottom_left",
    "bottom_center",
    "bottom_right",
    "center",
]


class OverlayClip(StrictModel):
    overlay_id: str = Field(min_length=1)
    asset_id: str = ""
    path: str = Field(min_length=1)
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(gt=0)
    anchor: OverlayAnchor = "top_center"
    margin_x: int = Field(default=0, ge=0)
    margin_y: int = Field(default=0, ge=0)
    width_ratio: float = Field(default=0.25, gt=0.0, le=1.0)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    z: int = Field(default=20, ge=0, le=1000)
    kind: Literal["image", "video"] = "image"
    layout: str = "fullscreen"
    ken_burns: bool = False
    transformative_crop: bool = False
    transition_in: str = ""
    transition_out: str = ""
    transition_frames: int = Field(default=6, ge=0, le=120)


class MulticamCut(StrictModel):
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    source_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end_frame <= self.start_frame:
            raise ValueError("multicam cut end must be after start")
        return self


class MulticamPlan(StrictModel):
    cuts: list[MulticamCut] = Field(default_factory=list)
    mode: str = "manual"


class TimeMapEntry(StrictModel):
    """One contiguous source-to-timeline mapping segment."""

    source_id: str = ""
    source_in_sample: int = Field(ge=0)
    source_out_sample: int = Field(ge=0)
    timeline_in_sample: int = Field(ge=0)
    timeline_out_sample: int = Field(ge=0)
    source_in_frame: int = Field(ge=0)
    source_out_frame: int = Field(ge=0)
    timeline_in_frame: int = Field(ge=0)
    timeline_out_frame: int = Field(ge=0)
    fps_num: int = Field(default=30, gt=0)
    fps_den: int = Field(default=1, gt=0)
    sample_rate: int = Field(default=48000, gt=0)


class PipelineCheckpoint(StrictModel):
    """One completed, skipped, or failed step in a tools-only run."""

    step: str = Field(min_length=1)
    status: Literal["completed", "failed", "skipped"] = "completed"
    started_at: str = ""
    finished_at: str = ""
    params_hash: str = ""
    revision: int = Field(default=0, ge=0)
    message: str = ""


class PipelineState(StrictModel):
    """Serializable bridge between tools-only MCP calls.

    The canonical timeline remains in :class:`ProjectState`; this block keeps
    the rest of :class:`PipelineContext` so a later tool call can resume without
    re-sending transcript, shorts, captions, artifacts, or analysis spans.
    """

    schema_version: Literal[1] = 1
    run_id: str = ""
    step: str = ""
    applied_style_id: str = ""
    artifacts: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    pcm_path: str = ""
    pcm_digest: str = ""
    speech_intervals: list[tuple[int, int]] = Field(default_factory=list)
    silence_spans: list[InactiveSpan] = Field(default_factory=list)
    retake_spans: list[InactiveSpan] = Field(default_factory=list)
    retake_overlap_cuts: list[tuple[int, int]] = Field(default_factory=list)
    inactive_spans: list[InactiveSpan] = Field(default_factory=list)
    vad_engine: str = "none"
    transcript_source: str = "none"
    transcript_language: str = ""
    language_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    discard_sentence_ids: list[int] = Field(default_factory=list)
    restored_sentence_ids: list[int] = Field(default_factory=list)
    manual_overrides: list[ManualOverride] = Field(default_factory=list)
    shorts: list[dict[str, Any]] = Field(default_factory=list)
    selected_shorts: list[dict[str, Any]] = Field(default_factory=list)
    short_captions: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    hashes: dict[str, str] = Field(default_factory=dict)
    cache_hits: list[str] = Field(default_factory=list)
    cache_misses: list[str] = Field(default_factory=list)
    time_map: list[TimeMapEntry] = Field(default_factory=list)
    checkpoints: list[PipelineCheckpoint] = Field(default_factory=list)


class SidecarPointer(StrictModel):
    """SHA-256 pointer to one sidecar document."""

    path: str = Field(min_length=1)
    sha256: str = ""
    bytes: int = Field(default=0, ge=0)
    sentences: int = Field(default=0, ge=0)
    segments: int = Field(default=0, ge=0)


class ProjectStateIndex(StrictModel):
    """Light ``state.json`` index introduced by the v4 layout."""

    schema_version: Literal[4] = 4
    pipeline_schema_version: str = "4.0"
    project_id: UUID = Field(default_factory=uuid4)
    slug: str = ""
    revision: int = Field(default=1, ge=1)
    updated_at: str = ""
    sidecars: dict[str, SidecarPointer] = Field(default_factory=dict)
    qa: list[SidecarPointer] = Field(default_factory=list)


class ProjectState(StrictModel):
    """The single JSON document under ``.videoflow/project_state.json``."""

    schema_version: Literal[4] = SCHEMA_VERSION
    project_id: UUID = Field(default_factory=uuid4)
    style_id: str = ""
    language: str = ""
    language_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    revision: int = Field(default=1, ge=1)
    media_info: MediaInfo | None = None
    sources: dict[str, MediaInfo] = Field(default_factory=dict)
    primary_source_id: str = ""
    source_offsets: dict[str, int] = Field(default_factory=dict)
    multicam: MulticamPlan | None = None
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
    inactive_segments: list[InactiveSegment] = Field(default_factory=list)
    vertical_clips: list[VerticalClip] = Field(default_factory=list)
    overlays: list[OverlayClip] = Field(default_factory=list)
    pipeline: PipelineState = Field(default_factory=PipelineState)

    @model_validator(mode="after")
    def unique_sentence_ids(self) -> Self:
        ids = [sentence.id for sentence in self.transcript]
        if len(ids) != len(set(ids)):
            raise ValueError("transcript sentence ids must be unique")
        if self.sources:
            if self.primary_source_id and self.primary_source_id not in self.sources:
                raise ValueError("primary_source_id is not present in sources")
            if not self.primary_source_id:
                self.primary_source_id = next(iter(self.sources))
            if self.media_info is None:
                self.media_info = self.sources[self.primary_source_id]
            for segment in self.video_segments:
                if not segment.source_id:
                    segment.source_id = self.primary_source_id
                if segment.source_id not in self.sources:
                    raise ValueError(f"video segment source_id is unknown: {segment.source_id}")
            for segment in self.audio_segments:
                if not segment.source_id:
                    segment.source_id = self.primary_source_id
                if segment.source_id not in self.sources:
                    raise ValueError(f"audio segment source_id is unknown: {segment.source_id}")
        return self

    def source_media(self, source_id: str | None = None) -> MediaInfo | None:
        """Resolve a source id to media info, falling back to the primary."""

        resolved = source_id or self.primary_source_id
        if resolved and resolved in self.sources:
            return self.sources[resolved]
        return self.media_info

    def video_media(self, clip: VideoSegment) -> MediaInfo | None:
        return self.source_media(clip.source_id)

    def audio_media(self, clip: AudioSegment) -> MediaInfo | None:
        return self.source_media(clip.source_id)

    def add_source(self, source_id: str, media: MediaInfo, *, primary: bool = False) -> None:
        self.sources[source_id] = media
        if primary or not self.primary_source_id:
            self.primary_source_id = source_id
            self.media_info = media


class LlmRetakeResponse(StrictModel):
    """The only payload the retake model is allowed to return."""

    discard_sentence_ids: list[int] = Field(default_factory=list)
    reasoning: str = Field(min_length=1)


class ShortsProposalClip(StrictModel):
    title: str = Field(min_length=1)
    sentence_ids: list[int] = Field(min_length=1)
    hook_sentence_id: int | None = None


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
