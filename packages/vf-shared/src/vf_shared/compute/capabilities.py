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
    "ingest_pcm": 0,
    "audio_finalize": 0,
}

CAPABILITIES = tuple(sorted(VRAM_COST_MB))

# Every worker capability can be slower than the controller CPU. ``selftest``
# stays local because it only probes the worker itself.
HEAVY_CAPABILITIES = frozenset(name for name in VRAM_COST_MB if name != "selftest")

_CAPABILITY_ALIASES = {
    "scene": "scene_analyze",
    "matte": "segment_matte",
    "shorts_render": "short_render",
    "audio_finalize": "audio_finalize",
    "ingest_pcm": "ingest_pcm",
}


def canonical_capability(name: str) -> str:
    """Map historical names used by callers to the worker capability."""

    clean = str(name or "").strip().lower()
    return _CAPABILITY_ALIASES.get(clean, clean)


def is_heavy_capability(name: str) -> bool:
    """Whether the capability should be forced onto the Windows worker."""

    return canonical_capability(name) in HEAVY_CAPABILITIES


def vram_cost(capability: str, default: int = 0) -> int:
    """Return the estimated VRAM for a capability."""

    return int(VRAM_COST_MB.get(canonical_capability(str(capability or "")), default))


__all__ = [
    "CAPABILITIES",
    "HEAVY_CAPABILITIES",
    "VRAM_COST_MB",
    "canonical_capability",
    "is_heavy_capability",
    "vram_cost",
]
