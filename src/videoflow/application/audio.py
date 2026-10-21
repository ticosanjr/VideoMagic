"""FFmpeg audio enhancement filters for rendered Shorts."""

from __future__ import annotations

from collections.abc import Sequence

from videoflow.domain.config import AudioEnhanceConfig


def audio_filters(config: AudioEnhanceConfig) -> list[str]:
    if not config.enabled:
        return []
    filters = [f"highpass=f={config.highpass_hz}"]
    if config.denoise:
        filters.append(
            f"afftdn=nr={config.denoise_db}:nf={config.noise_floor_db}"
        )
    if config.loudnorm:
        filters.append(
            f"loudnorm=I={config.target_lufs}:TP={config.true_peak_db}:LRA=11"
        )
    return filters


def with_audio_filters(filters: Sequence[str]) -> str | None:
    return ",".join(item for item in filters if item) or None
