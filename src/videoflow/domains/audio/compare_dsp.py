"""PCM, log-mel and window descriptors."""

# ruff: noqa: F401
from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from videoflow.domain.errors import IngestError
from videoflow.runtime import find_binary

SAMPLE_RATE = 16_000
FRAME_LENGTH = 400  # 25 ms
FRAME_HOP = 160  # 10 ms
N_MELS = 64
FMIN = 80.0
FMAX = 7600.0
WINDOW_FRAMES = 100  # 1 s
WINDOW_HOP = 50  # 0.5 s
SEGMENTS = 8
EPSILON = 1e-10


def load_pcm(
    path: Path,
    *,
    sample_rate: int = SAMPLE_RATE,
    timeout: float = 900.0,
) -> np.ndarray:
    """Decode the first audio stream to mono float32 PCM in ``[-1, 1]``."""

    binary = find_binary("ffmpeg")
    if binary is None:
        raise IngestError("FFmpeg is not available for audio comparison.")
    source = Path(path).expanduser()
    if not source.is_file():
        raise IngestError(f"Audio source does not exist: {source}")
    command = [
        binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "-",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IngestError(f"Audio decode failed: {exc}") from exc
    if result.returncode != 0 or not result.stdout:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise IngestError(f"Audio decode produced no PCM: {detail[:300]}")
    samples = np.frombuffer(result.stdout, dtype="<i2")
    if not samples.size:
        raise IngestError("Audio decode produced an empty stream.")
    return (samples.astype(np.float32) / 32768.0).copy()


def _hann(length: int) -> np.ndarray:
    return np.hanning(length).astype(np.float32)


def _hz_to_mel(value: float) -> float:
    return 2595.0 * math.log10(1.0 + value / 700.0)


def _mel_to_hz(value: float) -> float:
    return 700.0 * (10.0 ** (value / 2595.0) - 1.0)


def mel_filterbank(
    *,
    sample_rate: int = SAMPLE_RATE,
    n_fft: int = FRAME_LENGTH,
    n_mels: int = N_MELS,
    fmin: float = FMIN,
    fmax: float = FMAX,
) -> np.ndarray:
    """Return a triangular HTK mel filterbank with area normalisation."""

    low = _hz_to_mel(fmin)
    high = _hz_to_mel(min(fmax, sample_rate / 2))
    points = np.linspace(low, high, n_mels + 2)
    hz_points = np.asarray([_mel_to_hz(value) for value in points])
    bins = np.floor((n_fft + 1) * hz_points / sample_rate).astype(int)
    bins = np.clip(bins, 0, n_fft // 2)
    bank = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for index in range(n_mels):
        left, center, right = int(bins[index]), int(bins[index + 1]), int(bins[index + 2])
        center = max(center, left + 1)
        right = max(right, center + 1)
        for bin_index in range(left, min(center, bank.shape[1])):
            bank[index, bin_index] = (bin_index - left) / (center - left)
        for bin_index in range(center, min(right, bank.shape[1])):
            bank[index, bin_index] = (right - bin_index) / (right - center)
    widths = hz_points[2:] - hz_points[:-2]
    bank *= (2.0 / np.maximum(widths, 1e-6))[:, None]
    return bank


def log_mel(
    pcm: np.ndarray,
    *,
    sample_rate: int = SAMPLE_RATE,
    n_fft: int = FRAME_LENGTH,
    hop: int = FRAME_HOP,
    n_mels: int = N_MELS,
    fmin: float = FMIN,
    fmax: float = FMAX,
    chunk_frames: int = 4000,
) -> np.ndarray:
    """Compute a log-mel spectrogram in chunks to keep memory bounded."""

    signal = np.asarray(pcm, dtype=np.float32)
    if signal.ndim != 1:
        signal = signal.reshape(-1)
    if signal.size < n_fft:
        signal = np.pad(signal, (0, n_fft - signal.size))
    frame_count = 1 + (signal.size - n_fft) // hop
    usable = signal[: (frame_count - 1) * hop + n_fft]
    window = _hann(n_fft)
    bank = mel_filterbank(
        sample_rate=sample_rate,
        n_fft=n_fft,
        n_mels=n_mels,
        fmin=fmin,
        fmax=fmax,
    )
    output = np.empty((frame_count, n_mels), dtype=np.float32)
    for start in range(0, frame_count, chunk_frames):
        end = min(start + chunk_frames, frame_count)
        base = start * hop
        block = usable[base : base + (end - start - 1) * hop + n_fft]
        frames = np.lib.stride_tricks.sliding_window_view(block, n_fft)[::hop]
        spectrum = np.fft.rfft(frames * window, n=n_fft, axis=1)
        power = (spectrum.real**2 + spectrum.imag**2).astype(np.float32)
        mel = power @ bank.T
        output[start:end] = np.log(np.maximum(mel, EPSILON))
    return output


def frame_rms(
    pcm: np.ndarray,
    *,
    frame_length: int = FRAME_HOP,
    hop: int = FRAME_HOP,
) -> np.ndarray:
    """Return RMS per frame, using 10 ms frames by default."""

    signal = np.asarray(pcm, dtype=np.float32)
    if signal.ndim != 1:
        signal = signal.reshape(-1)
    if signal.size < frame_length:
        signal = np.pad(signal, (0, frame_length - signal.size))
    frame_count = 1 + (signal.size - frame_length) // hop
    usable = signal[: (frame_count - 1) * hop + frame_length]
    frames = np.lib.stride_tricks.sliding_window_view(usable, frame_length)[::hop]
    return np.sqrt(np.mean(frames * frames, axis=1)).astype(np.float32)


def speech_fraction(
    pcm: np.ndarray,
    *,
    window_frames: int = WINDOW_FRAMES,
    window_hop: int = WINDOW_HOP,
    threshold_db: float = -40.0,
) -> np.ndarray:
    """Return the fraction of active frames inside each analysis window."""

    rms = frame_rms(pcm)
    if rms.size == 0:
        return np.zeros(0, dtype=np.float32)
    relative = float(np.percentile(rms, 95)) * 0.05
    threshold = max(float(10 ** (threshold_db / 20.0)), relative)
    active = (rms > threshold).astype(np.float32)
    if active.size < window_frames:
        active = np.pad(active, (0, window_frames - active.size))
    windows = np.lib.stride_tricks.sliding_window_view(active, window_frames)[::window_hop]
    return windows.mean(axis=1).astype(np.float32)


def window_descriptors(
    features: np.ndarray,
    *,
    window_frames: int = WINDOW_FRAMES,
    window_hop: int = WINDOW_HOP,
    segments: int = SEGMENTS,
) -> np.ndarray:
    """Describe 1 s windows with per-segment mel mean and deviation.

    Mean-centring and L2 normalisation make the descriptor insensitive to gain
    and loudness differences between the reference and the rendered output.
    """

    data = np.asarray(features, dtype=np.float32)
    if data.ndim != 2:
        raise ValueError("features must be a 2-D matrix")
    if data.shape[0] < window_frames:
        data = np.pad(data, ((0, window_frames - data.shape[0]), (0, 0)), mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(data, window_frames, axis=0)[
        ::window_hop
    ]
    count = windows.shape[0]
    frames_per_segment = max(1, window_frames // segments)
    usable = frames_per_segment * segments
    shaped = windows[:, :, :usable].reshape(
        count, data.shape[1], segments, frames_per_segment
    )
    means = shaped.mean(axis=3)
    deviations = shaped.std(axis=3)
    descriptor = np.concatenate(
        (
            means.transpose(0, 2, 1).reshape(count, -1),
            deviations.transpose(0, 2, 1).reshape(count, -1),
        ),
        axis=1,
    )
    descriptor -= descriptor.mean(axis=1, keepdims=True)
    norm = np.linalg.norm(descriptor, axis=1, keepdims=True)
    descriptor /= np.maximum(norm, 1e-6)
    return descriptor.astype(np.float32)
