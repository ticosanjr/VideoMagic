"""Format presets for output geometry and safe zones."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AspectRatio = Literal["9:16", "4:5", "1:1", "16:9"]


class FormatDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=120)
    aspect_ratio: AspectRatio = "9:16"
    width: int = Field(default=1080, ge=240, le=7680)
    height: int = Field(default=1920, ge=240, le=7680)
    fps: int = Field(default=30, ge=12, le=120)
    safe_zones: dict[str, float] = Field(
        default_factory=lambda: {"bottom_px": 380.0, "right_px": 140.0}
    )
    caption_preset: str = "youtube_bold_yellow"
    platforms: list[str] = Field(default_factory=list)
    export_targets: list[str] = Field(default_factory=list)
    description: str = ""
    builtin: bool = False

    @model_validator(mode="after")
    def validate_aspect(self) -> FormatDefinition:
        expected = {
            "9:16": 9 / 16,
            "4:5": 4 / 5,
            "1:1": 1.0,
            "16:9": 16 / 9,
        }[self.aspect_ratio]
        actual = self.width / max(1, self.height)
        if abs(actual - expected) > 0.02:
            raise ValueError(
                f"width/height {self.width}x{self.height} does not match {self.aspect_ratio}"
            )
        return self


__all__ = ["AspectRatio", "FormatDefinition"]
