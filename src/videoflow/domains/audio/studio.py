"""Compatibility facade for the audio studio tools."""

from __future__ import annotations

from .studio_attach import attach_music_track
from .studio_common import AUDIO_EXTENSIONS, ROUTER
from .studio_mix import (
    build_mix_graph,
    generate_music_or_sfx,
    mix_and_master_track,
)
from .studio_tts import (
    build_voice_clean_filter,
    separate_audio_stems,
    tts_generate,
    voice_clean_and_enhance,
)

__all__ = [
    "AUDIO_EXTENSIONS",
    "ROUTER",
    "attach_music_track",
    "build_mix_graph",
    "build_voice_clean_filter",
    "generate_music_or_sfx",
    "mix_and_master_track",
    "separate_audio_stems",
    "tts_generate",
    "voice_clean_and_enhance",
]
