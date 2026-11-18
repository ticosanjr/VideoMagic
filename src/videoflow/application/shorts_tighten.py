"""VAD-driven Short edge and internal-silence tightening."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TightenedClip:
    start_sample: int
    end_sample: int
    pieces: tuple[tuple[int, int], ...]
    metrics: dict[str, Any]


def _clip_intervals(
    intervals: Sequence[tuple[int, int]], start: int, end: int
) -> list[tuple[int, int]]:
    return [
        (max(start, item_start), min(end, item_end))
        for item_start, item_end in intervals
        if item_end > start and item_start < end
    ]


def _metric_ms(samples: int, sample_rate: int) -> float:
    return round(samples / max(1, sample_rate) * 1000.0, 3)


def tighten_clip(
    *,
    start_sample: int,
    end_sample: int,
    speech_intervals: Sequence[tuple[int, int]],
    words: Sequence[Any],
    sample_rate: int,
    start_pad_ms: int = 80,
    end_pad_ms: int = 150,
    max_internal_silence_ms: int = 500,
    keep_silence_ms: int = 150,
    crossfade_ms: int = 15,
) -> TightenedClip:
    start = max(0, int(start_sample))
    end = max(start + 1, int(end_sample))
    word_starts = [
        int(word.start_sample)
        for word in words
        if int(word.end_sample) > start and int(word.start_sample) < end
    ]
    word_ends = [
        int(word.end_sample)
        for word in words
        if int(word.end_sample) > start and int(word.start_sample) < end
    ]
    first_word = min(word_starts) if word_starts else start
    last_word = max(word_ends) if word_ends else end
    padded_start = max(start, first_word - round(start_pad_ms * sample_rate / 1000))
    padded_end = min(end, last_word + round(end_pad_ms * sample_rate / 1000))
    slots = _clip_intervals(speech_intervals, start, end)
    if slots:
        padded_start = max(padded_start, min(item[0] for item in slots))
        padded_end = min(padded_end, max(item[1] for item in slots))
    pieces: list[tuple[int, int]] = []
    maximum_gap = round(max_internal_silence_ms * sample_rate / 1000)
    for item_start, item_end in slots:
        if item_end <= padded_start or item_start >= padded_end:
            continue
        item_start = max(padded_start, item_start)
        item_end = min(padded_end, item_end)
        if not pieces:
            pieces.append((item_start, item_end))
            continue
        previous_start, previous_end = pieces[-1]
        gap = item_start - previous_end
        if gap <= maximum_gap:
            pieces[-1] = (previous_start, item_end)
        else:
            pieces.append((item_start, item_end))
    if not pieces:
        pieces = [(padded_start, padded_end)]
        slots = pieces
    total = max(1, sum(item_end - item_start for item_start, item_end in pieces))
    speech_total = sum(
        max(0, min(item_end, end) - max(item_start, start))
        for item_start, item_end in slots
    )
    internal_gaps = 0
    for left, right in zip(slots, slots[1:], strict=False):
        internal_gaps = max(internal_gaps, right[0] - left[1])
    metrics = {
        "speech_ratio": round(min(1.0, speech_total / total), 4),
        "edge_silence_start_ms": _metric_ms(first_word - start, sample_rate),
        "edge_silence_end_ms": _metric_ms(end - last_word, sample_rate),
        "max_internal_silence_ms": _metric_ms(internal_gaps, sample_rate),
        "first_word_start": round(first_word / max(1, sample_rate), 6),
        "last_word_end": round(last_word / max(1, sample_rate), 6),
        "pieces": len(pieces),
        "crossfade_ms": crossfade_ms,
    }
    return TightenedClip(
        start_sample=pieces[0][0],
        end_sample=pieces[-1][1],
        pieces=tuple(pieces),
        metrics=metrics,
    )


def passes_metrics(metrics: dict[str, Any]) -> bool:
    return (
        float(metrics.get("speech_ratio") or 0.0) >= 0.85
        and float(metrics.get("edge_silence_start_ms") or 0.0) <= 300.0
        and float(metrics.get("edge_silence_end_ms") or 0.0) <= 400.0
        and float(metrics.get("max_internal_silence_ms") or 0.0) <= 700.0
    )


__all__ = ["TightenedClip", "passes_metrics", "tighten_clip"]
