"""Vision tools: captions, mattes, upscale, motion graphics and B-roll."""

from __future__ import annotations

from ..toolkit.errors import MediaToolError
from .broll import build_broll_filter, image_to_broll_motion
from .captions import segments_to_ass, segments_to_srt, transcribe_word_aligned
from .capture import capture_web_or_screen
from .matte import remove_background
from .motion import render_motion_graphic
from .upscale import upscale_media

__all__ = [
    "build_broll_filter",
    "capture_web_or_screen",
    "image_to_broll_motion",
    "MediaToolError",
    "remove_background",
    "render_motion_graphic",
    "segments_to_ass",
    "segments_to_srt",
    "transcribe_word_aligned",
    "upscale_media",
]
