"""Registration and warmup for optional built-in GPU handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gpu_worker.gpu_handlers.asr import (
    _ASR_LOCK,
    _ASR_MODELS,
    make_asr_handler,
    make_forced_align_handler,
)
from gpu_worker.gpu_handlers.audio import (
    make_audio_finalize_handler,
    make_ingest_pcm_handler,
)
from gpu_worker.gpu_handlers.common import (
    _available,
    _binary_available,
    _ffmpeg,
    _import_error,
    nvenc_available,
)
from gpu_worker.gpu_handlers.matte import _matte_session, make_segment_matte_handler
from gpu_worker.gpu_handlers.render import (
    make_ffmpeg_transcode_handler,
    make_render_nvenc_handler,
    make_short_render_handler,
)
from gpu_worker.gpu_handlers.scene import make_scene_analyze_handler
from gpu_worker.gpu_handlers.vision import make_face_track_handler, make_vision_blur_handler
from gpu_worker.handlers import HandlerRegistry

if TYPE_CHECKING:
    from gpu_worker.models import ModelRegistry
    from gpu_worker.settings import Settings

def warmup_models(
    settings: Settings,
    models: ModelRegistry | None = None,
) -> dict[str, Any]:
    """Preload expensive models so the first job does not pay cold start.

    Failures are reported, never raised: a missing optional dependency or an
    offline model download must not stop the worker from serving the
    capabilities it does have.
    """

    loaded: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    model_name = settings.asr_model or "large-v3-turbo"
    key = (model_name, settings.asr_device or "cuda", settings.asr_compute_type or "float16")
    asr_error = _import_error("faster_whisper")
    if asr_error:
        skipped.append(f"asr: {asr_error}")
    else:
        try:
            from faster_whisper import WhisperModel

            with _ASR_LOCK:
                if key not in _ASR_MODELS:
                    _ASR_MODELS[key] = WhisperModel(
                        key[0],
                        device=key[1],
                        compute_type=key[2],
                        cpu_threads=int(settings.asr_cpu_threads or 0),
                        num_workers=int(settings.asr_num_workers or 1),
                    )
                    if models is not None:
                        model_key = f"faster-whisper:{key[0]}:{key[1]}:{key[2]}"

                        def unload_asr() -> None:
                            _ASR_MODELS.pop(key, None)

                        models.register(
                            model_key,
                            capability="asr",
                            unload=unload_asr,
                            vram_mb=3277,
                            metadata={"model": key[0], "device": key[1]},
                        )
            loaded.append(f"faster-whisper:{key[0]}")
        except Exception as exc:  # noqa: BLE001 - warmup is best-effort
            errors.append(f"asr: {exc}")
    if not _available("rembg"):
        skipped.append("matte: rembg is not installed")
    else:
        try:
            _matte_session("u2net", models)
            loaded.append("rembg:u2net")
        except Exception as exc:  # noqa: BLE001 - warmup is best-effort
            errors.append(f"matte: {exc}")
    return {
        "ok": not errors,
        "loaded": loaded,
        "skipped": skipped,
        "errors": errors,
    }


def register_builtin_handlers(
    registry: HandlerRegistry,
    settings: Settings,
    models: ModelRegistry | None = None,
) -> None:
    """Register optional Python handlers, marking missing dependencies."""

    asr_error = _import_error("faster_whisper")
    if not asr_error:
        try:
            registry.register_handler("asr", make_asr_handler(settings, models))
            registry.register_handler(
                "forced_align", make_forced_align_handler(settings)
            )
        except Exception as exc:  # noqa: BLE001 - optional handler cannot kill startup
            reason = f"ASR handler init failed: {type(exc).__name__}: {exc}"
            registry.mark_unavailable("asr", reason)
            registry.mark_unavailable("forced_align", reason)
    else:
        registry.mark_unavailable("asr", asr_error)
        registry.mark_unavailable("forced_align", asr_error)
    if nvenc_available(_ffmpeg(settings)):
        registry.register_handler("render_nvenc", make_render_nvenc_handler(settings))
    else:
        registry.mark_unavailable(
            "render_nvenc", "FFmpeg does not expose h264_nvenc"
        )
    if _available("rembg"):
        registry.register_handler(
            "segment_matte", make_segment_matte_handler(settings, models)
        )
    else:
        registry.mark_unavailable("segment_matte", "rembg is not installed")
    if _available("cv2"):
        registry.register_handler("face_track", make_face_track_handler(settings))
        registry.register_handler(
            "vision_blur", make_vision_blur_handler(settings)
        )
        registry.register_handler(
            "scene_analyze", make_scene_analyze_handler(settings)
        )
    else:
        registry.mark_unavailable("face_track", "OpenCV is not installed")
        registry.mark_unavailable("vision_blur", "OpenCV is not installed")
        registry.mark_unavailable("scene_analyze", "OpenCV is not installed")
    if _binary_available(_ffmpeg(settings)):
        registry.register_handler(
            "short_render", make_short_render_handler(settings)
        )
        registry.register_handler(
            "ffmpeg_transcode", make_ffmpeg_transcode_handler(settings)
        )
        registry.register_handler(
            "ingest_pcm", make_ingest_pcm_handler(settings)
        )
        registry.register_handler(
            "audio_finalize", make_audio_finalize_handler(settings)
        )
    else:
        for capability in ("short_render", "ingest_pcm", "audio_finalize"):
            registry.mark_unavailable(capability, "FFmpeg is not available")
    registry.mark_unavailable(
        "audio_events", "YAMNet ONNX model is not configured on the worker"
    )


__all__ = [
    "make_asr_handler",
    "make_face_track_handler",
    "make_forced_align_handler",
    "make_render_nvenc_handler",
    "make_scene_analyze_handler",
    "warmup_models",
]

