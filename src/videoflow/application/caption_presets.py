"""Named kinetic caption presets."""

from __future__ import annotations

from typing import Any

PRESETS: dict[str, dict[str, Any]] = {
    "kinetic_highlight": {
        "font_size": 70,
        "font_weight": "bold",
        "uppercase": True,
        "primary_color": "#FFFFFF",
        "highlight_color": "#00D4FF",
        "keyword_color": "#00D4FF",
        "outline_width": 4,
        "animation": "sweep",
        "word_timing": "word",
        "keyword_highlight_enabled": True,
    },
    "word_highlight_blue": {
        "font_size": 72,
        "font_weight": "bold",
        "uppercase": True,
        "primary_color": "#FFFFFF",
        "highlight_color": "#2563EB",
        "keyword_color": "#38BDF8",
        "outline_width": 5,
        "animation": "pop",
        "word_timing": "word",
        "keyword_highlight_enabled": True,
    },
    "high_contrast_box": {
        "font_size": 62,
        "font_weight": "bold",
        "uppercase": True,
        "primary_color": "#FFFFFF",
        "background_color": "#000000",
        "background_opacity": 0.82,
        "background_padding": 16,
        "outline_width": 0,
        "animation": "none",
        "word_timing": "word",
    },
    "karaoke_emoji": {
        "font_size": 70,
        "font_weight": "bold",
        "uppercase": True,
        "highlight_color": "#FACC15",
        "outline_width": 4,
        "animation": "sweep",
        "word_timing": "word",
        "keyword_highlight_enabled": True,
        "emoji_enabled": True,
    },
    "clean_lower_third": {
        "font_size": 52,
        "font_weight": "normal",
        "uppercase": False,
        "primary_color": "#FFFFFF",
        "background_color": "#000000",
        "background_opacity": 0.55,
        "background_padding": 10,
        "alignment": 2,
        "position_y": 0.86,
        "animation": "none",
        "word_timing": "sentence",
    },

    "tiktok_bold": {
        "font_size": 72,
        "font_weight": "bold",
        "uppercase": True,
        "outline_width": 4,
        "animation": "pop",
        "word_timing": "engine",
        "keyword_highlight_enabled": True,
        "emoji_enabled": True,
    },
    "minimalist_box": {
        "font_size": 54,
        "font_weight": "normal",
        "uppercase": False,
        "background_opacity": 0.65,
        "background_padding": 12,
        "animation": "none",
        "word_timing": "sentence",
    },
    "highlight_word": {
        "font_size": 64,
        "font_weight": "bold",
        "uppercase": False,
        "highlight_color": "#FFD400",
        "keyword_highlight_enabled": True,
        "animation": "sweep",
        "word_timing": "engine",
    },
    "hormozi_bold": {
        "font_size": 84,
        "font_weight": "bold",
        "uppercase": True,
        "primary_color": "#FFFFFF",
        "highlight_color": "#00FF66",
        "outline_width": 6,
        "animation": "pop",
        "word_timing": "engine",
        "keyword_highlight_enabled": True,
        "keyword_color": "#00FF66",
        "emoji_enabled": True,
    },
    "beast_highlight": {
        "font_size": 76,
        "font_weight": "bold",
        "uppercase": True,
        "primary_color": "#FFFFFF",
        "highlight_color": "#FF3B30",
        "outline_color": "#000000",
        "outline_width": 5,
        "animation": "sweep",
        "word_timing": "engine",
        "keyword_highlight_enabled": True,
        "keyword_color": "#FFD400",
    },
    "clean_white": {
        "font_size": 56,
        "font_weight": "normal",
        "uppercase": False,
        "primary_color": "#FFFFFF",
        "outline_width": 2,
        "shadow_opacity": 0.35,
        "animation": "none",
        "word_timing": "engine",
    },
    "podcast_speaker": {
        "font_size": 60,
        "font_weight": "bold",
        "uppercase": False,
        "outline_width": 3,
        "animation": "none",
        "word_timing": "engine",
        "speaker_colors": ["#FFFFFF", "#00E5FF", "#FFD400", "#FF6B6B"],
    },
}


def apply_preset(name: str, style: Any, *, strict: bool = True) -> Any:
    """Return a caption style with the named preset overrides applied.

    Unknown presets fail loudly when ``strict`` is true; the style compiler and
    render steps no longer fall back silently to the default look.
    """

    overrides = PRESETS.get(name)
    if not overrides:
        if strict and str(name or "").strip():
            raise ValueError(f"unknown caption preset: {name}")
        return style
    return style.model_copy(update=overrides)
