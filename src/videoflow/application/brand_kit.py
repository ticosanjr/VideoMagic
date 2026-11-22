"""Channel brand-kit discovery for logos, lower thirds, CTAs, LUTs, and stings."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from pydantic import Field

from videoflow.core.recipe import Recipe
from videoflow.domain.config import (
    CaptionStyle,
    IntroOutroConfig,
    MusicConfig,
    OverlayConfig,
    StrictModel,
)
from videoflow.domain.errors import FilesystemError, StateNotReadyError
from videoflow.domain.headless import PresetRulebook
from videoflow.domain.presets import SHIPPED_PRESET_NAMES
from videoflow.runtime import portable_home
from videoflow.steps.registry import get_step

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".m4v"}
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".ogg"}


def brand_kit_root(channel_id: str) -> Path:
    return portable_home() / "brands" / str(channel_id).strip()


def load_brand_kit(channel_id: str) -> dict[str, Any]:
    root = brand_kit_root(channel_id)
    if not root.is_dir():
        return {"channel_id": channel_id, "path": str(root), "exists": False, "assets": {}}
    assets: dict[str, list[str]] = {
        "logo": [],
        "lower_third": [],
        "cta": [],
        "lut": [],
        "music": [],
        "sting": [],
    }
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.casefold()
        name = path.name.casefold()
        if suffix == ".cube":
            assets["lut"].append(str(path))
        elif "logo" in name and suffix in IMAGE_SUFFIXES:
            assets["logo"].append(str(path))
        elif ("lower" in name or "third" in name) and suffix in IMAGE_SUFFIXES:
            assets["lower_third"].append(str(path))
        elif ("cta" in name or "card" in name) and suffix in IMAGE_SUFFIXES | VIDEO_SUFFIXES:
            assets["cta"].append(str(path))
        elif suffix in AUDIO_SUFFIXES and ("sting" in name or "vignette" in name):
            assets["sting"].append(str(path))
        elif suffix in AUDIO_SUFFIXES:
            assets["music"].append(str(path))
    return {
        "channel_id": channel_id,
        "path": str(root),
        "exists": True,
        "assets": assets,
        "logo": assets["logo"][0] if assets["logo"] else "",
        "lower_third": assets["lower_third"][0] if assets["lower_third"] else "",
        "cta": assets["cta"][0] if assets["cta"] else "",
        "lut": assets["lut"][0] if assets["lut"] else "",
        "music": assets["music"][0] if assets["music"] else "",
        "sting": assets["sting"][0] if assets["sting"] else "",
    }


__all__ = [
    "BrandTemplate",
    "apply_brand_options",
    "apply_brand_kit",
    "brand_kit_root",
    "brand_kit_ids",
    "delete_template",
    "get_template",
    "is_brand_kit",
    "list_templates",
    "load_brand_kit",
    "save_template",
]


def _is_empty(value: Any) -> bool:
    """Return True for the placeholder values a kit may safely override."""

    return value is None or value == "" or value == [] or value == {}


def _merge_defaults(params: dict[str, Any], defaults: dict[str, Any]) -> None:
    for key, value in defaults.items():
        if key not in params or _is_empty(params[key]):
            params[key] = deepcopy(value)


def brand_kit_ids() -> list[str]:
    """Return the channel kit ids accepted by ``vf_project``."""

    from videoflow.application.preset_rules import channel_dir

    ids = set(SHIPPED_PRESET_NAMES)
    try:
        directory = channel_dir()
        if directory.is_dir():
            ids.update(path.stem for path in directory.glob("*.json"))
    except Exception:  # noqa: BLE001 - settings may be unavailable
        pass
    return sorted(ids)


def is_brand_kit(channel_id: str) -> bool:
    return (channel_id or "").strip() in set(brand_kit_ids())


def apply_brand_kit(recipe: Recipe, book: PresetRulebook) -> Recipe:
    """Return a copy with kit defaults and inviolable hard constraints."""

    updated = recipe.model_copy(deep=True)
    kit = book.brand_kit
    hard = book.hard_constraints
    for step in updated.steps:
        params = step.params if isinstance(step.params, dict) else {}
        step.params = params
        try:
            allowed = set(get_step(step.type).params_model.model_fields)
        except Exception:  # noqa: BLE001 - validation reports the unknown step later
            allowed = set()
        step_defaults = kit.defaults.get(step.type) if isinstance(kit.defaults, dict) else None
        if isinstance(step_defaults, dict):
            _merge_defaults(
                params,
                {key: value for key, value in step_defaults.items() if key in allowed},
            )
        if hard.aspect_ratio and "aspect_ratio" in allowed:
            params["aspect_ratio"] = hard.aspect_ratio
        if hard.caption_preset and "preset" in allowed and not params.get("preset"):
            params["preset"] = hard.caption_preset
        if "caption_style" in allowed and not isinstance(
            params.get("caption_style"), (dict, type(None))
        ):
            params["caption_style"] = {}
        if kit.intro and "intro_path" in allowed and not params.get("intro_path"):
            params["intro_path"] = kit.intro
        if kit.outro and "outro_path" in allowed and not params.get("outro_path"):
            params["outro_path"] = kit.outro
        if kit.music and "music_path" in allowed and not params.get("music_path"):
            params["music_path"] = kit.music[0]
        if kit.lut and "lut_path" in allowed and not params.get("lut_path"):
            params["lut_path"] = kit.lut
        if hard.broll_style and "query" in allowed and not params.get("query"):
            params["query"] = hard.broll_style
    return updated


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
            "caption_effect": style.effect,
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
