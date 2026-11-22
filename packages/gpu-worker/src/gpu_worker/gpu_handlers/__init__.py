"""Built-in GPU handlers split by capability family."""

from gpu_worker.gpu_handlers.asr import (
    _ASR_LOCK,
    _ASR_MODELS,
    make_asr_handler,
    make_forced_align_handler,
)
from gpu_worker.gpu_handlers.common import (
    _NVENC_CACHE,
    _NVENC_PROBES,
    _NVENC_REASONS,
    NvencProbe,
    _available,
    _binary_available,
    _escape_filter_path,
    _ffmpeg,
    _run,
    _run_in,
    nvenc_advice,
    nvenc_args,
    nvenc_available,
    nvenc_error,
    probe_nvenc,
)
from gpu_worker.gpu_handlers.matte import (
    _MATTE_LOCK,
    _MATTE_SESSIONS,
    IMAGE_SUFFIXES,
    _matte_session,
    make_segment_matte_handler,
)
from gpu_worker.gpu_handlers.registry import register_builtin_handlers, warmup_models
from gpu_worker.gpu_handlers.render import (
    make_ffmpeg_transcode_handler,
    make_render_nvenc_handler,
    make_short_render_handler,
)
from gpu_worker.gpu_handlers.scene import (
    _scene_ffmpeg_times,
    _scene_hints,
    _scene_keyframes,
    _scene_layout,
    make_scene_analyze_handler,
)
from gpu_worker.gpu_handlers.scene_visual import (
    _scene_face_backend,
    _scene_median,
    _scene_sample_times,
    _scene_visuals,
)
from gpu_worker.gpu_handlers.vision import (
    make_face_track_handler,
    make_vision_blur_handler,
)

__all__ = [
    "IMAGE_SUFFIXES",
    "_ASR_LOCK",
    "_ASR_MODELS",
    "_MATTE_LOCK",
    "_MATTE_SESSIONS",
    "_NVENC_CACHE",
    "_NVENC_PROBES",
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
    "make_ffmpeg_transcode_handler",
    "make_forced_align_handler",
    "make_render_nvenc_handler",
    "make_scene_analyze_handler",
    "make_short_render_handler",
    "make_segment_matte_handler",
    "make_vision_blur_handler",
    "NvencProbe",
    "nvenc_advice",
    "nvenc_args",
    "nvenc_available",
    "nvenc_error",
    "probe_nvenc",
    "register_builtin_handlers",
    "warmup_models",
]
