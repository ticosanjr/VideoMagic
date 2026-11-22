"""Interval, silence, loudness and spectral metrics."""


# ruff: noqa: E402,F401,F403,F405
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


from .compare_dsp import _hann, frame_rms, load_pcm


def interval_union(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Merge overlapping or touching intervals."""

    ordered = sorted((max(0.0, start), max(0.0, end)) for start, end in intervals)
    merged: list[tuple[float, float]] = []
    for start, end in ordered:
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def interval_duration(intervals: list[tuple[float, float]]) -> float:
    return sum(end - start for start, end in interval_union(intervals))


def interval_overlap(
    left: list[tuple[float, float]],
    right: list[tuple[float, float]],
) -> float:
    """Return the total intersection duration of two interval sets."""

    a = interval_union(left)
    b = interval_union(right)
    total = 0.0
    first = second = 0
    while first < len(a) and second < len(b):
        start = max(a[first][0], b[second][0])
        end = min(a[first][1], b[second][1])
        if end > start:
            total += end - start
        if a[first][1] < b[second][1]:
            first += 1
        else:
            second += 1
    return total


def interval_f1(
    reference: list[tuple[float, float]],
    output: list[tuple[float, float]],
    *,
    tolerance: float = 0.15,
) -> dict[str, float]:
    """Time-weighted precision/recall/F1 with a boundary tolerance."""

    reference_intervals = interval_union(reference)
    output_intervals = interval_union(output)
    reference_duration = interval_duration(reference_intervals)
    output_duration = interval_duration(output_intervals)
    if reference_duration <= 0 or output_duration <= 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "tolerance": tolerance}
    dilated_output = [(start - tolerance, end + tolerance) for start, end in output_intervals]
    dilated_reference = [
        (start - tolerance, end + tolerance) for start, end in reference_intervals
    ]
    covered_reference = interval_overlap(reference_intervals, dilated_output)
    covered_output = interval_overlap(output_intervals, dilated_reference)
    recall = min(1.0, covered_reference / reference_duration)
    precision = min(1.0, covered_output / output_duration)
    denominator = precision + recall
    f1 = 2.0 * precision * recall / denominator if denominator > 0 else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tolerance": tolerance,
    }


def silence_spans(
    pcm: np.ndarray,
    *,
    sample_rate: int = SAMPLE_RATE,
    threshold_db: float = -35.0,
    min_ms: int = 100,
    frame_ms: int = 10,
) -> list[tuple[float, float]]:
    """Return silence runs in seconds using the same profile as the edit."""

    signal = np.asarray(pcm, dtype=np.float32)
    frame_length = max(1, round(sample_rate * frame_ms / 1000))
    rms = frame_rms(signal, frame_length=frame_length, hop=frame_length)
    if rms.size == 0:
        return []
    threshold = float(10 ** (threshold_db / 20.0))
    silent = rms <= threshold
    minimum = max(1, round(min_ms / frame_ms))
    spans: list[tuple[float, float]] = []
    start: int | None = None
    for index, value in enumerate(silent):
        if value and start is None:
            start = index
        elif not value and start is not None:
            if index - start >= minimum:
                spans.append(
                    (
                        start * frame_ms / 1000,
                        index * frame_ms / 1000,
                    )
                )
            start = None
    if start is not None and len(silent) - start >= minimum:
        spans.append((start * frame_ms / 1000, len(silent) * frame_ms / 1000))
    return spans


def silence_stats(spans: list[tuple[float, float]]) -> dict[str, float]:
    total = sum(end - start for start, end in spans)
    maximum = max((end - start for start, end in spans), default=0.0)
    return {
        "total_seconds": round(total, 3),
        "max_seconds": round(maximum, 3),
        "events": len(spans),
    }


def loudness_stats(path: Path) -> dict[str, float | None]:
    """Measure integrated loudness and true peak with FFmpeg loudnorm."""

    binary = find_binary("ffmpeg")
    if binary is None:
        return {"lufs": None, "true_peak": None, "lra": None}
    command = [
        binary,
        "-hide_banner",
        "-nostats",
        "-i",
        str(Path(path).expanduser()),
        "-map",
        "0:a:0",
        "-af",
        "loudnorm=print_format=json",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=900.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"lufs": None, "true_peak": None, "lra": None}
    text = result.stderr.decode("utf-8", errors="replace")
    start = text.rfind("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return {"lufs": None, "true_peak": None, "lra": None}
    try:
        import json

        payload = json.loads(text[start : end + 1])
    except ValueError:
        return {"lufs": None, "true_peak": None, "lra": None}

    def value(key: str) -> float | None:
        try:
            return float(payload[key])
        except (KeyError, TypeError, ValueError):
            return None

    return {
        "lufs": value("input_i"),
        "true_peak": value("input_tp"),
        "lra": value("input_lra"),
    }


def spectral_correlation(
    reference_pcm: np.ndarray,
    output_pcm: np.ndarray,
    *,
    sample_rate: int = SAMPLE_RATE,
    n_fft: int = 2048,
    hop: int = 1024,
) -> float:
    """Correlate long-term average spectra on a common frequency grid."""

    def average_spectrum(pcm: np.ndarray) -> np.ndarray:
        signal = np.asarray(pcm, dtype=np.float32)
        if signal.size < n_fft:
            signal = np.pad(signal, (0, n_fft - signal.size))
        frame_count = 1 + (signal.size - n_fft) // hop
        usable = signal[: (frame_count - 1) * hop + n_fft]
        frames = np.lib.stride_tricks.sliding_window_view(usable, n_fft)[::hop]
        window = _hann(n_fft)
        spectrum = np.fft.rfft(frames * window, axis=1)
        power = spectrum.real**2 + spectrum.imag**2
        return np.mean(power, axis=0)

    reference = average_spectrum(reference_pcm)
    output = average_spectrum(output_pcm)
    size = min(reference.size, output.size)
    reference = reference[:size]
    output = output[:size]
    reference = 10.0 * np.log10(np.maximum(reference, EPSILON))
    output = 10.0 * np.log10(np.maximum(output, EPSILON))
    if reference.size < 2:
        return 0.0
    reference -= reference.mean()
    output -= output.mean()
    denominator = float(np.linalg.norm(reference) * np.linalg.norm(output))
    if denominator <= 0:
        return 0.0
    return float(np.dot(reference, output) / denominator)


def reconstruct(
    pcm: np.ndarray,
    intervals: list[tuple[float, float]],
    *,
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    """Concatenate source PCM at the given source-time intervals."""

    chunks: list[np.ndarray] = []
    limit = pcm.size
    for start, end in interval_union(intervals):
        start_sample = max(0, min(limit, round(start * sample_rate)))
        end_sample = max(start_sample, min(limit, round(end * sample_rate)))
        if end_sample > start_sample:
            chunks.append(pcm[start_sample:end_sample])
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks)
