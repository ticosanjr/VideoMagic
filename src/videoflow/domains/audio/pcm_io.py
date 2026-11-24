"""One PCM reader for signed 16/24/32-bit WAV files.

WAV frames are aligned to ``sampwidth * channels`` bytes. A truncated final
frame must be ignored, never passed to ``numpy.frombuffer`` as a partial item.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


def _decode(raw: bytes, *, sample_width: int) -> np.ndarray:
    if sample_width == 2:
        return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if sample_width == 3:
        values = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        samples = values[:, 0] | (values[:, 1] << 8) | (values[:, 2] << 16)
        samples = np.where(samples & 0x800000, samples - 0x1000000, samples)
        return samples.astype(np.float32) / 8388608.0
    if sample_width == 4:
        return np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    raise ValueError(f"Unsupported PCM sample width: {sample_width}")


def read_wav_mono_float32(path: Path | str) -> tuple[np.ndarray, int]:
    """Read a signed PCM WAV and return mono float32 samples plus sample rate.

    The returned samples are in ``-1.0..1.0``. A partial trailing frame is
    discarded. Width 1 (8-bit unsigned) and compressed WAV formats fail closed.
    """

    source = Path(path).expanduser()
    with wave.open(str(source), "rb") as handle:
        channels = max(1, int(handle.getnchannels()))
        width = int(handle.getsampwidth())
        rate = int(handle.getframerate())
        raw = handle.readframes(handle.getnframes())
    if width not in {2, 3, 4}:
        raise ValueError(f"Unsupported PCM sample width: {width}")
    if rate <= 0:
        raise ValueError("WAV sample rate must be positive")
    frame_bytes = width * channels
    usable = len(raw) - (len(raw) % frame_bytes)
    if usable <= 0:
        return np.zeros(0, dtype=np.float32), rate
    samples = _decode(raw[:usable], sample_width=width)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return np.ascontiguousarray(samples, dtype=np.float32), rate


def decode_pcm_mono_rms(data: bytes, *, sampwidth: int, channels: int) -> int:
    """Return RMS in the signed 16-bit domain, truncating incomplete frames."""

    if sampwidth not in {2, 3, 4}:
        raise ValueError(f"Unsupported PCM sample width: {sampwidth}")
    channels = max(1, int(channels))
    frame = sampwidth * channels
    usable = len(data) - (len(data) % frame)
    if usable <= 0:
        return 0
    samples = _decode(data[:usable], sample_width=sampwidth)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if samples.size == 0:
        return 0
    total = float(np.dot(samples, samples))
    return int(np.sqrt(total / samples.size) * 32768.0)


__all__ = ["decode_pcm_mono_rms", "read_wav_mono_float32"]
