"""Canonical channel style definitions stored as Markdown + YAML frontmatter."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from videoflow.domain.headless import PresetRule

STYLE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
STYLE_EXPORT_TARGETS = ("mp4_youtube", "resolve", "premiere", "kdenlive")
LAYOUT_MODES = {
    "auto",
    "full_screen",
    "fullscreen",
    "cutout",
    "rounded_window",
    "multicam_auto",
    "split_top_visual",
    "pip_bottom_right",
    "split_screen_50_50",
    "headline_card",
    "fullscreen_punchin",
    "fullscreen_motion",
    "active_speaker_reframe",
    "presenter_collage",
}
MOTION_ENGINES = {
    "auto",
    "ffmpeg",
    "hyperframes",
    "remotion",
    "html",
    "manim",
    "ffmpeg+hyperframes",
}


class StyleDefinition(BaseModel):
    """One style file under ``{data}/styles/<style_id>.md``."""

    model_config = ConfigDict(extra="allow")

    schema_version: int = Field(default=2, ge=1, le=2)
    version: int = Field(default=1, ge=1)
    style_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    aspect_ratio: str = Field(default="", max_length=20)
    format_id: str = Field(default="", max_length=80)
    target_lufs: float = Field(default=-16.0, ge=-30.0, le=-5.0)
    max_static_sec: float = Field(default=4.0, ge=0.1, le=120.0)
    min_silence_ms: int = Field(default=400, ge=0, le=10_000)
    layout_mode: str = Field(default="", max_length=40)
    caption_preset: str = Field(default="", max_length=80)
    motion_engine: str = Field(default="auto", max_length=40)
    platforms: list[str] = Field(default_factory=list)
    beatmap_defaults: dict[str, Any] = Field(default_factory=dict)
    sound_design: dict[str, Any] = Field(default_factory=dict)
    hook_strategy: str = Field(default="", max_length=400)
    intro_strategy: str = Field(default="", max_length=400)
    export_targets: list[str] = Field(default_factory=lambda: list(STYLE_EXPORT_TARGETS))
    palette: list[str] = Field(default_factory=list)
    fonts: list[str] = Field(default_factory=list)
    cut_rhythm: dict[str, Any] = Field(default_factory=dict)
    safe_zones: dict[str, Any] = Field(default_factory=dict)
    learned_rules: list[PresetRule] = Field(default_factory=list, max_length=15)
    body: str = ""
    updated_at: str = ""

    @field_validator("style_id")
    @classmethod
    def valid_style_id(cls, value: str) -> str:
        if not STYLE_ID_RE.fullmatch(value):
            raise ValueError("style_id must match [a-z0-9][a-z0-9._-]{0,79}")
        return value

    @field_validator("layout_mode")
    @classmethod
    def valid_layout(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized and normalized not in LAYOUT_MODES:
            raise ValueError(f"unknown layout_mode: {value}")
        return normalized

    @field_validator("motion_engine")
    @classmethod
    def valid_motion_engine(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized and normalized not in MOTION_ENGINES:
            raise ValueError(f"unknown motion_engine: {value}")
        return normalized

    @field_validator("platforms")
    @classmethod
    def unique_platforms(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        for item in value:
            name = str(item).strip().lower()
            if name and name not in seen:
                seen.append(name)
        return seen

    @field_validator("export_targets")
    @classmethod
    def unique_targets(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        for item in value:
            name = str(item).strip().lower()
            if name and name not in seen:
                seen.append(name)
        return seen

    @property
    def summary(self) -> str:
        first_bullet = ""
        for line in self.body.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("- "):
                first_bullet = first_bullet or stripped[2:].strip()
                continue
            return stripped[:240]
        return first_bullet[:240] or self.name


__all__ = [
    "LAYOUT_MODES",
    "MOTION_ENGINES",
    "STYLE_EXPORT_TARGETS",
    "STYLE_ID_RE",
    "StyleDefinition",
]
