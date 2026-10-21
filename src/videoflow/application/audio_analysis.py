"""Lightweight audio-energy peak detection for Short curation."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from videoflow.domain.errors import IngestError
from videoflow.runtime import find_binary


def energy_peaks(
    samples: np.ndarray,
    sample_rate: int,
    *,
    window_ms: int = 100,
    threshold: float = 1.5,
    min_gap_ms: int = 200,
) -> list[tuple[int, int]]:
    if sample_rate <= 0 or len(samples) == 0:
        return []
    window = max(1, sample_rate * max(20, window_ms) // 1000)
    count = len(samples) // window
    if count == 0:
        return []
    values = samples[: count * window].astype(np.float64).reshape(count, window)
    rms = np.sqrt((values * values).mean(axis=1))
    if float(rms.max()) <= 1e-6:
        return []
    threshold_value = float(rms.mean() + threshold * rms.std())
    active = rms >= threshold_value
    if not active.any():
        return []
    peaks: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(active):
        if value and start is None:
            start = index
        elif not value and start is not None:
            peaks.append((start * window, index * window))
            start = None
    if start is not None:
        peaks.append((start * window, len(active) * window))
    gap = sample_rate * max(0, min_gap_ms) // 1000
    merged: list[tuple[int, int]] = []
    for start, end in peaks:
        if merged and start - merged[-1][1] <= gap:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def detect_audio_energy(
    source: Path,
    sample_rate: int,
    *,
    timeout: float = 300.0,
) -> list[tuple[int, int]]:
    binary = find_binary("ffmpeg")
    if binary is None:
        raise IngestError("FFmpeg is not available for audio analysis.")
    command = [
        binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(Path(source).expanduser()),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
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
        raise IngestError(f"Audio analysis failed: {exc}") from exc
    if result.returncode != 0 or not result.stdout:
        raise IngestError("Audio analysis produced no PCM.")
    samples = np.frombuffer(result.stdout, dtype=np.int16)
    peaks = energy_peaks(samples, 16000)
    scale = sample_rate / 16000
    return [
        (round(start * scale), round(end * scale))
        for start, end in peaks
    ]
