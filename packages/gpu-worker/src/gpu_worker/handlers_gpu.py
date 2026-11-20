"""Backward-compatible facade for the split built-in GPU handlers.

New code should import from ``gpu_worker.gpu_handlers``. This module keeps the
historical ``gpu_worker.handlers_gpu`` import path and private test helpers.
"""

from __future__ import annotations

from gpu_worker.gpu_handlers import (
    make_asr_handler,
    make_face_track_handler,
    make_forced_align_handler,
    make_render_nvenc_handler,
    make_scene_analyze_handler,
    make_segment_matte_handler,
    make_short_render_handler,
    make_vision_blur_handler,
    nvenc_available,
    nvenc_error,
    register_builtin_handlers,
    warmup_models,
)
from gpu_worker.gpu_handlers.asr import _ASR_LOCK, _ASR_MODELS
from gpu_worker.gpu_handlers.common import (
    _NVENC_CACHE,
    _NVENC_REASONS,
    _available,
    _binary_available,
    _escape_filter_path,
    _ffmpeg,
    _run,
    _run_in,
)
from gpu_worker.gpu_handlers.matte import (
    _MATTE_LOCK,
    _MATTE_SESSIONS,
    IMAGE_SUFFIXES,
    _matte_session,
)
from gpu_worker.gpu_handlers.scene import (
    _scene_face_backend,
    _scene_ffmpeg_times,
    _scene_hints,
    _scene_keyframes,
    _scene_layout,
    _scene_median,
    _scene_sample_times,
    _scene_visuals,
)

__all__ = [
    "IMAGE_SUFFIXES",
    "_ASR_LOCK",
    "_ASR_MODELS",
    "_MATTE_LOCK",
    "_MATTE_SESSIONS",
    "_NVENC_CACHE",
    "_NVENC_REASONS",
    "_available",
    "_binary_available",
    "_escape_filter_path",
    "_ffmpeg",
    "_matte_session",
    "_run",
    "_run_in",
    "_scene_face_backend",
    "_scene_ffmpeg_times",
    "_scene_hints",
    "_scene_keyframes",
    "_scene_layout",
    "_scene_median",
    "_scene_sample_times",
    "_scene_visuals",
    "make_asr_handler",
    "make_face_track_handler",
    "make_forced_align_handler",
    "make_render_nvenc_handler",
    "make_scene_analyze_handler",
    "make_segment_matte_handler",
    "make_short_render_handler",
    "make_vision_blur_handler",
    "nvenc_available",
    "nvenc_error",
    "register_builtin_handlers",
    "warmup_models",
]
