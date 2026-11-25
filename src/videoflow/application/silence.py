"""Audio-level silence detection and timeline silence capping.

Word timestamps are useful for text, but they often include silence inside a
"word". The reference edit keeps short natural pauses (up to about half a
second) and removes the rest. These helpers measure silence on the PCM and cap
long runs after the content cuts are already decided.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from videoflow.domain.state import InactiveSpan
from videoflow.domains.audio.pcm_io import read_wav_mono_float32

PACING_PROFILES: dict[str, dict[str, int]] = {
    "tight": {
        "min_silence_ms": 300,
        "max_pause_ms": 260,
        "pad_before_ms": 85,
        "pad_after_ms": 130,
        "qa_dead_air_ms": 650,
        "min_cut_gap_ms": 140,
    },
    "balanced": {
        "min_silence_ms": 380,
        "max_pause_ms": 400,
        "pad_before_ms": 90,
        "pad_after_ms": 130,
        "qa_dead_air_ms": 900,
        "min_cut_gap_ms": 200,
    },
    "relaxed": {
        "min_silence_ms": 550,
        "max_pause_ms": 700,
        "pad_before_ms": 120,
        "pad_after_ms": 170,
        "qa_dead_air_ms": 1200,
        "min_cut_gap_ms": 260,
    },
}


def resolve_pacing_profile(
    profile: str = "tight",
    *,
    min_silence_ms: int | None = None,
    max_pause_ms: int | None = None,
    pad_before_ms: int | None = None,
    pad_after_ms: int | None = None,
    qa_dead_air_ms: int | None = None,
    min_cut_gap_ms: int | None = None,
) -> dict[str, int]:
    """Resolve one pacing profile with explicit per-run overrides."""

    key = str(profile or "tight").strip().lower()
    values = dict(PACING_PROFILES.get(key, PACING_PROFILES["tight"]))
    for name, value in (
        ("min_silence_ms", min_silence_ms),
        ("max_pause_ms", max_pause_ms),
        ("pad_before_ms", pad_before_ms),
        ("pad_after_ms", pad_after_ms),
        ("qa_dead_air_ms", qa_dead_air_ms),
        ("min_cut_gap_ms", min_cut_gap_ms),
    ):
        if value is not None:
            values[name] = max(0, int(value))
    values["qa_dead_air_ms"] = max(
        int(values.get("qa_dead_air_ms") or 0),
        int(round(values["max_pause_ms"] * 1.8)),
        500,
    )
    return values


def detect_silence_spans(
    path: Path | None,
    *,
    sample_rate: int,
    frame_ms: int = 10,
    threshold_db: float = -35.0,
    min_ms: int = 100,
) -> list[tuple[int, int]]:
    """Return source sample spans whose RMS is below ``threshold_db``.

    Spans are quantised to ``frame_ms`` and shorter runs than ``min_ms`` are
    dropped, matching the measurement used on the human reference edit.
    """

    if path is None or not path.is_file() or frame_ms <= 0:
        return []
    try:
        samples, rate = read_wav_mono_float32(path)
    except (OSError, EOFError, ValueError):
        return []
    if rate <= 0 or samples.size == 0:
        return []
    frame_samples = max(1, round(rate * frame_ms / 1000))
    threshold = 10 ** (threshold_db / 20.0)
    minimum = max(1, round(min_ms * rate / 1000))
    count = samples.size // frame_samples
    if count <= 0:
        return []
    frames = samples[: count * frame_samples].reshape(count, frame_samples)
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    silent = rms <= threshold
    spans: list[tuple[int, int]] = []
    position = 0
    silence_start: int | None = None
    while position < count:
        if silent[position] and silence_start is None:
            silence_start = position * frame_samples
        elif not silent[position] and silence_start is not None:
            end = position * frame_samples
            if end - silence_start >= minimum:
                spans.append((silence_start, end))
            silence_start = None
        position += 1
    if silence_start is not None and count * frame_samples - silence_start >= minimum:
        spans.append((silence_start, count * frame_samples))
    if rate != sample_rate:
        scale = sample_rate / rate
        spans = [
            (round(start * scale), round(end * scale))
            for start, end in spans
        ]
    return spans


def cap_silence_spans(
    spans: list[tuple[int, int]],
    silences: list[tuple[int, int]] | list[InactiveSpan],
    *,
    sample_rate: int,
    max_silence_ms: int = 500,
    keep_silence_ms: int = 300,
    pad_before_ms: int = 20,
    pad_after_ms: int = 40,
    min_clip_ms: int = 200,
) -> tuple[list[tuple[int, int]], float]:
    """Cap silence runs inside kept spans while preserving short pauses."""

    max_samples = max(0, round(max_silence_ms * sample_rate / 1000))
    keep_samples = max(0, round(keep_silence_ms * sample_rate / 1000))
    before = max(0, round(pad_before_ms * sample_rate / 1000))
    after = max(0, round(pad_after_ms * sample_rate / 1000))
    minimum = max(1, round(min_clip_ms * sample_rate / 1000))
    silence_tuples = [
        (item.start_sample, item.end_sample)
        if isinstance(item, InactiveSpan)
        else (item[0], item[1])
        for item in silences
    ]
    silence_tuples.sort()
    output: list[tuple[int, int]] = []
    removed = 0
    for start, end in spans:
        cuts: list[tuple[int, int]] = []
        for silence_start, silence_end in silence_tuples:
            if silence_end <= start or silence_start >= end:
                continue
            overlap_start = max(start, silence_start)
            overlap_end = min(end, silence_end)
            length = overlap_end - overlap_start
            if length <= max_samples:
                continue
            leading = overlap_start <= start + 1
            trailing = overlap_end >= end - 1
            if leading and trailing:
                cuts.append((start, end))
                continue
            if leading:
                cut_start = start
                cut_end = max(start, overlap_end - before)
                if cut_end > cut_start:
                    cuts.append((cut_start, cut_end))
            elif trailing:
                cut_start = min(end, overlap_start + after)
                cut_end = end
                if cut_end > cut_start:
                    cuts.append((cut_start, cut_end))
            else:
                left_keep = keep_samples // 2
                right_keep = keep_samples - left_keep
                cut_start = overlap_start + left_keep
                cut_end = overlap_end - right_keep
                if cut_end > cut_start:
                    cuts.append((cut_start, cut_end))
        cuts.sort()
        merged_cuts: list[tuple[int, int]] = []
        for cut_start, cut_end in cuts:
            if merged_cuts and cut_start <= merged_cuts[-1][1]:
                merged_cuts[-1] = (merged_cuts[-1][0], max(merged_cuts[-1][1], cut_end))
            else:
                merged_cuts.append((cut_start, cut_end))
        cursor = start
        for cut_start, cut_end in merged_cuts:
            if cut_start > cursor:
                output.append((cursor, cut_start))
            removed += max(0, cut_end - max(cursor, cut_start))
            cursor = max(cursor, cut_end)
        if end > cursor:
            output.append((cursor, end))
    filtered = [(a, b) for a, b in output if b - a >= minimum]
    if len(filtered) != len(output):
        removed += sum(
            b - a for a, b in output if b - a < minimum
        )
    return filtered, removed / sample_rate
