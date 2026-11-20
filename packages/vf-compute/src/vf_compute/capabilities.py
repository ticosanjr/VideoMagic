"""Default capability names and VRAM estimates shared by router and worker."""

from __future__ import annotations

# Keep in sync with packages/gpu-worker/src/gpu_worker/capabilities.py.
VRAM_COST_MB: dict[str, int] = {
    "selftest": 0,
    "asr": 3277,
    "forced_align": 3277,
    "scene_analyze": 1024,
    "short_render": 1024,
    "ffmpeg_transcode": 0,
    "audio_events": 512,
    "vision_blur": 512,
    "render_nvenc": 820,
    "segment_matte": 1536,
    "face_track": 1024,
    "stems": 2048,
    "upscale": 2560,
    "tts": 1024,
    "music": 1536,
    "sfx": 1024,
    "diarize": 2048,
    "comfyui": 4096,
}

CAPABILITIES = tuple(sorted(VRAM_COST_MB))


def vram_cost(capability: str, default: int = 0) -> int:
    """Return the estimated VRAM for a capability."""

    return int(VRAM_COST_MB.get(str(capability or "").lower(), default))


__all__ = ["CAPABILITIES", "VRAM_COST_MB", "vram_cost"]
