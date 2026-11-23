"""Canonical media constants (schema 4.0)."""

from __future__ import annotations

from typing import Literal

MediaKind = Literal[
    "source",
    "audio_master",
    "audio_delivery",
    "overlay",
    "deliverable",
]
PIPELINE_SCHEMA_VERSION = "4.0"
TARGET_LUFS = -16.0
TOLERANCE_LUFS = 1.5
LOUDNORM_TARGET_TP_DB = -2.0
QA_MAX_TRUE_PEAK_DBTP = -1.0
TRUE_PEAK_MAX = LOUDNORM_TARGET_TP_DB
TARGET_LRA = 9
ALPHA_PIX_FMTS = frozenset({"yuva420p", "yuva444p10le", "rgba", "bgra", "argb", "abgr"})
SDR_PIX_FMTS = frozenset({"yuv420p", "yuvj420p", "yuv422p", "yuv444p"})
AUDIO_MASTER_RATE = 48_000
AUDIO_MASTER_CHANNELS = 2
AUDIO_MASTER_CODEC = "pcm_s24le"
AUDIO_DELIVERY_CODECS = frozenset({"aac", "libfdk_aac"})
AUDIO_DELIVERY_MIN_BITRATE = 192_000
