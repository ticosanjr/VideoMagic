"""Dynamic Shorts composition contract.

The LLM may return scene ids or relative times. Validation lives here so the
renderer never receives gaps, overlaps, unknown layouts, or unsafe durations.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ShortLayout = Literal[
    "FULL_FACE",
    "SPLIT_BROLL",
    "SPLIT_SCREEN_SAFE",
    "SPLIT_SCREEN_FILL",
]
SourceTopology = Literal["single_16x9", "dual_canvas", "dual_file"]


class BrollSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["local_file", "stock"] = "local_file"
    path: str = ""
    fallback_query: str = ""


class ScreenFocus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["full_width", "roi"] = "full_width"
    roi_x: float = Field(default=0.5, ge=0.0, le=1.0)
    roi_y: float = Field(default=0.5, ge=0.0, le=1.0)
    zoom: float = Field(default=1.0, ge=1.0, le=2.5)


class ShortSegmentBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seg_id: str = Field(min_length=1)
    layout: ShortLayout
    face_zoom: float = Field(default=1.0, ge=1.0, le=1.12)
    broll_source: BrollSource | None = None
    screen_focus: ScreenFocus | None = None
    sfx_on_enter: str | None = None
    start_scene_id: str = ""
    end_scene_id: str = ""


class ShortSegment(ShortSegmentBase):
    rel_start: float = Field(ge=0.0)
    rel_end: float = Field(gt=0.0)

    @model_validator(mode="after")
    def valid_span(self) -> ShortSegment:
        if self.rel_end <= self.rel_start:
            raise ValueError("segment rel_end must be after rel_start")
        return self


class ShortSegmentDraft(ShortSegmentBase):
    rel_start: float | None = Field(default=None, ge=0.0)
    rel_end: float | None = Field(default=None, gt=0.0)

    @model_validator(mode="after")
    def anchored(self) -> ShortSegmentDraft:
        if self.rel_start is None and not self.start_scene_id:
            raise ValueError("segment needs rel_start or start_scene_id")
        if self.rel_end is None and not self.end_scene_id:
            raise ValueError("segment needs rel_end or end_scene_id")
        if (
            self.rel_start is not None
            and self.rel_end is not None
            and self.rel_end <= self.rel_start
        ):
            raise ValueError("segment rel_end must be after rel_start")
        return self


class ShortCompositionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    short_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    source_video_path: str = ""
    source_topology: SourceTopology = "single_16x9"
    start: float = Field(ge=0.0)
    end: float = Field(gt=0.0)
    end_padding_ms: int = Field(default=350, ge=0, le=2000)
    target_fps: int = Field(default=30, ge=15, le=60)
    subtitle_style: str = "youtube_bold_yellow"
    target_width: int = Field(default=1080, ge=1080, le=1080)
    target_height: int = Field(default=1920, ge=1920, le=1920)
    segments: list[ShortSegment] = Field(default_factory=list)

    @model_validator(mode="after")
    def continuous_coverage(self) -> ShortCompositionPlan:
        if self.end <= self.start:
            raise ValueError("plan end must be after start")
        if not self.segments:
            raise ValueError("plan needs at least one segment")
        ordered = sorted(self.segments, key=lambda item: item.rel_start)
        if ordered[0].rel_start > 1e-6:
            raise ValueError("segments must start at rel_start=0")
        for index, segment in enumerate(ordered):
            if index and abs(segment.rel_start - ordered[index - 1].rel_end) > 1e-5:
                raise ValueError("segments must be contiguous without gaps or overlaps")
        duration = self.duration_sec
        if abs(ordered[-1].rel_end - duration) > 1e-3:
            raise ValueError("segments must cover the full plan duration")
        if any(segment.rel_end - segment.rel_start < 2.5 for segment in ordered):
            raise ValueError("each segment must be at least 2.5 seconds")
        return self

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.end - self.start)


class ShortCompositionDraft(BaseModel):
    """Agent/LLM plan before scene ids are converted to relative times."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    short_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    source_video_path: str = ""
    source_topology: SourceTopology = "single_16x9"
    start: float = Field(ge=0.0)
    end: float = Field(gt=0.0)
    end_padding_ms: int = Field(default=350, ge=0, le=2000)
    target_fps: int = Field(default=30, ge=15, le=60)
    subtitle_style: str = "youtube_bold_yellow"
    target_width: int = Field(default=1080, ge=1080, le=1080)
    target_height: int = Field(default=1920, ge=1920, le=1920)
    segments: list[ShortSegmentDraft] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_bounds(self) -> ShortCompositionDraft:
        if self.end <= self.start:
            raise ValueError("plan end must be after start")
        if not self.segments:
            raise ValueError("plan needs at least one segment")
        return self

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.end - self.start)


class ShortPlanResponse(BaseModel):
    """LLM response: scene anchors only, no absolute timestamps."""

    model_config = ConfigDict(extra="forbid")

    short_id: str = Field(
        default="", pattern=r"^$|^[A-Za-z0-9][A-Za-z0-9_-]*$"
    )
    segments: list[ShortSegmentDraft] = Field(default_factory=list)


__all__ = [
    "BrollSource",
    "ScreenFocus",
    "ShortCompositionDraft",
    "ShortCompositionPlan",
    "ShortLayout",
    "ShortPlanResponse",
    "ShortSegment",
    "ShortSegmentBase",
    "ShortSegmentDraft",
    "SourceTopology",
]
