"""Canonical media contract shared by ingest, render, export, and QA."""

from __future__ import annotations

from videoflow.core.media_contract.audio import (
    assert_pcm_buffer,
    channel_rms,
    needs_mono_repair,
    repair_mono_file,
)
from videoflow.core.media_contract.constants import (
    ALPHA_PIX_FMTS,
    AUDIO_DELIVERY_CODECS,
    AUDIO_DELIVERY_MIN_BITRATE,
    AUDIO_MASTER_CHANNELS,
    AUDIO_MASTER_CODEC,
    AUDIO_MASTER_RATE,
    PIPELINE_SCHEMA_VERSION,
    SDR_PIX_FMTS,
    TARGET_LRA,
    TARGET_LUFS,
    TOLERANCE_LUFS,
    TRUE_PEAK_MAX,
    MediaKind,
)
from videoflow.core.media_contract.models import (
    ExpectedMedia,
    MediaContractError,
    MediaReport,
)
from videoflow.core.media_contract.policy import (
    color_profile,
    source_needs_normalization,
)
from videoflow.core.media_contract.validate import (
    assert_media,
    validate_alpha,
    validate_media,
)

__all__ = [
    "ALPHA_PIX_FMTS",
    "AUDIO_DELIVERY_CODECS",
    "AUDIO_DELIVERY_MIN_BITRATE",
    "AUDIO_MASTER_CHANNELS",
    "AUDIO_MASTER_CODEC",
    "AUDIO_MASTER_RATE",
    "PIPELINE_SCHEMA_VERSION",
    "SDR_PIX_FMTS",
    "TARGET_LRA",
    "TARGET_LUFS",
    "TOLERANCE_LUFS",
    "TRUE_PEAK_MAX",
    "ExpectedMedia",
    "MediaContractError",
    "MediaKind",
    "MediaReport",
    "assert_media",
    "assert_pcm_buffer",
    "channel_rms",
    "color_profile",
    "needs_mono_repair",
    "repair_mono_file",
    "source_needs_normalization",
    "validate_alpha",
    "validate_media",
]
