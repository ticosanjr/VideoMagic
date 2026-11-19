"""Sample-exact RMS envelopes for acoustic cut placement.

The envelope is computed at the project audio rate so every value maps directly
to the same integer samples used by the timeline. A 10 ms hop with a 25 ms
window gives a stable map without loading the whole recording into memory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from videoflow.application.non_speech import load_pcm_mono


def build_rms_profile(
    path: Path | None,
    *,
    sample_rate: int,
    frame_ms: int = 10,
    window_ms: int = 25,
) -> dict[str, Any]:
    """Return a compact dBFS envelope for one PCM file."""

    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if frame_ms <= 0 or window_ms <= 0:
        raise ValueError("frame_ms and window_ms must be positive")

    samples = load_pcm_mono(path, sample_rate=sample_rate)
    hop = max(1, round(sample_rate * frame_ms / 1000))
    window = max(hop, round(sample_rate * window_ms / 1000))
    count = 0 if samples.size < window else 1 + (samples.size - window) // hop
    if count <= 0:
        return {
            "schema_version": 1,
            "sample_rate": sample_rate,
            "frame_ms": frame_ms,
            "window_ms": window_ms,
            "hop_samples": hop,
            "window_samples": window,
            "count": 0,
            "db": [],
        }

    squares = np.square(samples[: window + (count - 1) * hop], dtype=np.float64)
    cumulative = np.concatenate(([0.0], np.cumsum(squares)))
    starts = np.arange(count, dtype=np.int64) * hop
    energy = cumulative[starts + window] - cumulative[starts]
    values = np.sqrt(np.maximum(energy, 0.0) / window)
    db = 20.0 * np.log10(np.maximum(values, 1e-9))
    return {
        "schema_version": 1,
        "sample_rate": sample_rate,
        "frame_ms": frame_ms,
        "window_ms": window_ms,
        "hop_samples": hop,
        "window_samples": window,
        "count": int(count),
        "db": [round(float(value), 2) for value in db],
    }


def rms_db_at(profile: dict[str, Any], sample: int) -> float:
    """Return the dBFS value covering ``sample`` (clamped to the profile)."""

    hop = int(profile.get("hop_samples") or 1)
    values = profile.get("db") or []
    if not values:
        return -120.0
    index = max(0, min(len(values) - 1, int(sample) // max(1, hop)))
    return float(values[index])


def rms_mean_db(profile: dict[str, Any], start: int, end: int) -> float:
    """Mean dBFS over a source-sample interval."""

    values = profile.get("db") or []
    hop = int(profile.get("hop_samples") or 1)
    if not values:
        return -120.0
    first = max(0, start // hop)
    last = min(len(values) - 1, max(first, end // hop))
    if last < first:
        return float(values[first])
    return round(sum(float(value) for value in values[first : last + 1]) / (last - first + 1), 2)


def min_rms_index(profile: dict[str, Any], start: int, end: int) -> int:
    """Index of the quietest hop inside ``[start, end)`` in source samples."""

    values = profile.get("db") or []
    if not values:
        return max(0, start)
    hop = int(profile.get("hop_samples") or 1)
    first = max(0, start // hop)
    last = min(len(values) - 1, max(first, end // hop))
    if last < first:
        return first
    index = min(range(first, last + 1), key=lambda item: values[item])
    return index * hop
