"""Capabilities implemented by the GPU worker and their VRAM estimates."""

from __future__ import annotations

# Keep in sync with packages/vf-compute/src/vf_compute/capabilities.py.
VRAM_COST_MB: dict[str, int] = {
    "asr": 3277,
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

BUILTIN_CAPABILITIES = tuple(sorted(VRAM_COST_MB))


def vram_cost(capability: str, default: int = 0) -> int:
    """Estimate the VRAM needed by one capability."""

    return int(VRAM_COST_MB.get(str(capability or "").lower(), default))


__all__ = ["BUILTIN_CAPABILITIES", "VRAM_COST_MB", "vram_cost"]
