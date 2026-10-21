"""Reusable brand templates for Shorts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import Field

from videoflow.domain.config import (
    CaptionStyle,
    IntroOutroConfig,
    MusicConfig,
    OverlayConfig,
    StrictModel,
)
from videoflow.domain.errors import FilesystemError, StateNotReadyError
from videoflow.runtime import portable_home


class BrandTemplate(StrictModel):
    name: str
    description: str = ""
    caption_style: CaptionStyle = Field(default_factory=CaptionStyle)
    overlay: OverlayConfig = Field(default_factory=OverlayConfig)
    music: MusicConfig = Field(default_factory=MusicConfig)
    intro_outro: IntroOutroConfig = Field(default_factory=IntroOutroConfig)


def templates_dir() -> Path:
    directory = portable_home() / "brand_templates"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def list_templates() -> list[dict[str, object]]:
    templates: list[dict[str, object]] = []
    for path in sorted(templates_dir().glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["name"] = str(payload.get("name") or path.stem)
            templates.append(payload)
        except (OSError, ValueError):
            continue
    return templates


def get_template(name: str) -> BrandTemplate:
    path = _path(name)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise StateNotReadyError(f"Brand template not found: {name}") from exc
    except ValueError as exc:
        raise FilesystemError(f"Brand template is invalid: {exc}") from exc
    payload["name"] = name
    return BrandTemplate.model_validate(payload)


def save_template(template: BrandTemplate) -> dict[str, object]:
    path = _path(template.name)
    path.write_text(
        json.dumps(template.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return template.model_dump(mode="json")


def delete_template(name: str) -> None:
    path = _path(name)
    if not path.is_file():
        raise StateNotReadyError(f"Brand template not found: {name}")
    path.unlink()


def apply_brand_options(options: dict[str, Any], name: str) -> dict[str, Any]:
    template = get_template(name)
    merged = dict(options)
    style = template.caption_style
    merged.update(
        {
            "caption_font_family": style.font_family,
            "caption_font_size": style.font_size,
            "caption_font_weight": style.font_weight,
            "caption_italic": style.italic,
            "caption_uppercase": style.uppercase,
            "caption_primary_color": style.primary_color,
            "caption_highlight_color": style.highlight_color,
            "caption_outline_color": style.outline_color,
            "caption_outline_width": style.outline_width,
            "caption_shadow_color": style.shadow_color,
            "caption_shadow_offset": style.shadow_offset,
            "caption_shadow_opacity": style.shadow_opacity,
            "caption_background_color": style.background_color,
            "caption_background_opacity": style.background_opacity,
            "caption_background_padding": style.background_padding,
            "caption_alignment": style.alignment,
            "caption_position_x": style.position_x,
            "caption_position_y": style.position_y,
            "caption_max_width": style.max_width,
            "caption_animation": style.animation,
            "caption_word_timing": style.word_timing,
            "caption_censor_enabled": style.censor_enabled,
            "caption_censor_words": style.censor_words,
            "caption_censor_replacement": style.censor_replacement,
            "caption_keyword_highlight_enabled": style.keyword_highlight_enabled,
            "caption_keyword_color": style.keyword_color,
            "caption_keyword_words": style.keyword_words,
            "caption_emoji_enabled": style.emoji_enabled,
            "caption_emoji_map": style.emoji_map,
            "caption_brand_vocabulary": style.brand_vocabulary,
            "overlay_enabled": template.overlay.enabled,
            "overlay_asset": template.overlay.asset,
            "overlay_position": template.overlay.position,
            "overlay_margin_px": template.overlay.margin_px,
            "overlay_width_ratio": template.overlay.width_ratio,
            "overlay_opacity": template.overlay.opacity,
            "music_enabled": template.music.enabled,
            "music_asset": template.music.asset,
            "music_volume": template.music.volume,
            "music_ducking": template.music.ducking,
            "music_fade_in_ms": template.music.fade_in_ms,
            "music_fade_out_ms": template.music.fade_out_ms,
            "intro_enabled": template.intro_outro.intro_enabled,
            "intro_asset": template.intro_outro.intro_asset,
            "intro_duration_sec": template.intro_outro.intro_duration_sec,
            "outro_enabled": template.intro_outro.outro_enabled,
            "outro_asset": template.intro_outro.outro_asset,
            "outro_duration_sec": template.intro_outro.outro_duration_sec,
        }
    )
    return merged


def _path(name: str) -> Path:
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", name.strip().casefold()).strip("-")
    if not cleaned:
        raise FilesystemError("Brand template name is empty.")
    return templates_dir() / f"{cleaned}.json"
