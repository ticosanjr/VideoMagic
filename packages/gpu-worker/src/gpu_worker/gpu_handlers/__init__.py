"""Built-in GPU handlers split by capability family."""

from gpu_worker.gpu_handlers.asr import make_asr_handler, make_forced_align_handler
from gpu_worker.gpu_handlers.common import (
    NvencProbe,
    nvenc_advice,
    nvenc_args,
    nvenc_available,
    nvenc_error,
    probe_nvenc,
)
from gpu_worker.gpu_handlers.matte import make_segment_matte_handler
from gpu_worker.gpu_handlers.registry import register_builtin_handlers, warmup_models
from gpu_worker.gpu_handlers.render import (
    make_render_nvenc_handler,
    make_short_render_handler,
)
from gpu_worker.gpu_handlers.scene import make_scene_analyze_handler
from gpu_worker.gpu_handlers.vision import (
    make_face_track_handler,
    make_vision_blur_handler,
)

__all__ = [
    "make_asr_handler",
    "make_face_track_handler",
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
