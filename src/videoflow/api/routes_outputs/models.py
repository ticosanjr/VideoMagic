"""Request models for output routes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ShortDubbingRequest(BaseModel):
    text: str | None = None
    target_language: str = Field(default="en", min_length=2, max_length=20)
    base_url: str | None = None
    model: str = "tts-1"
    voice: str = "alloy"
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    volume: float = Field(default=1.0, ge=0.0, le=1.0)
    original_volume: float = Field(default=0.0, ge=0.0, le=1.0)
    llm_base_url: str | None = None
    llm_model: str = "qwen2.5:7b-instruct"
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)


class StepOutputSaveRequest(BaseModel):
    target_dir: str = Field(min_length=1)


class ArtifactUpdateRequest(BaseModel):
    payload: dict[str, Any]


class ReviewDecisionRequest(BaseModel):
    approved: bool
    comment: str = Field(default="", max_length=4000)
    reviewer: str = Field(default="", max_length=120)


class ThumbnailSelectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)


class ThumbnailMetricRequest(BaseModel):
    impressions: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)


class ReviewCommentRequest(BaseModel):
    author: str = Field(default="local operator", max_length=120)
    text: str = Field(min_length=1, max_length=4000)
    time_sec: float | None = Field(default=None, ge=0.0)


class BrollApprovalRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    approved: list[int] = Field(default_factory=list)
    order: list[int] = Field(default_factory=list)


class ShortVoiceoverRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    provider: Literal["openai_compatible", "piper"] = "openai_compatible"
    base_url: str | None = None
    model: str = "tts-1"
    voice: str = "alloy"
    binary: str = "piper"
    model_path: str = ""
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    volume: float = Field(default=1.0, ge=0.0, le=1.0)
    original_volume: float = Field(default=0.35, ge=0.0, le=1.0)
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)


class ShortThumbnailRequest(BaseModel):
    time_sec: float | None = Field(default=None, ge=0.0)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    caption_style: dict[str, Any] | None = None


class ShortVisionRequest(BaseModel):
    base_url: str | None = None
    model: str = "gpt-4o-mini"
    max_frames: int = Field(default=6, ge=1, le=12)
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)


class ShortEmojiRequest(BaseModel):
    base_url: str | None = None
    model: str = "qwen2.5:7b-instruct"
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)


class ShortMetadataRequest(BaseModel):
    platform: Literal["youtube", "tiktok", "instagram", "linkedin"] = "youtube"
    tone: Literal["engaging", "professional", "educational", "bold"] = "engaging"
    extra_hashtags: list[str] = Field(default_factory=list)


class ShortEditRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    start_sec: float | None = Field(default=None, ge=0.0)
    end_sec: float | None = Field(default=None, ge=0.0)
    aspect_ratio: Literal["9:16", "1:1", "16:9"] | None = None
    burn_subtitles: bool | None = None
    caption_style: dict[str, Any] | None = None

    @model_validator(mode="after")
    def ordered_trim(self) -> ShortEditRequest:
        if (
            self.end_sec is not None
            and self.start_sec is not None
            and self.end_sec <= self.start_sec
        ):
            raise ValueError("end_sec must be greater than start_sec")
        return self


