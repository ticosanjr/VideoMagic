"""Word-integrity policy for the cut timeline.

Every word the editor decided to keep must be fully inside one kept span. A
silence cap, a noise removal, or a word cut must never leave half a word. This
module measures that invariant and repairs the safe cases by merging the two
pieces of a split word.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from videoflow.application.spans import merge_spans

_LETTER = re.compile(r"[^a-z0-9à-ÿ]")


def _removed(
    word_start: int,
    word_end: int,
    removed_spans: Sequence[tuple[int, int]],
) -> bool:
    if not removed_spans:
        return False
    midpoint = (word_start + word_end) // 2
    return any(start <= midpoint <= end for start, end in removed_spans)


def _kept_words(
    transcript: Sequence[Any],
    discard_ids: set[int],
    removed_spans: Sequence[tuple[int, int]],
    *,
    max_word_ms: int,
    sample_rate: int,
) -> list[tuple[int, int]]:
    maximum = max(1, round(max_word_ms * sample_rate / 1000))
    words: list[tuple[int, int]] = []
    for sentence in transcript:
        if sentence.id in discard_ids:
            continue
        for word in sentence.words:
            if word.end_sample <= word.start_sample:
                continue
            letters = len(_LETTER.sub("", word.word.casefold()))
            plausible_ms = min(max_word_ms, 150 + 60 * max(1, letters))
            plausible = max(1, round(plausible_ms * sample_rate / 1000))
            if word.end_sample - word.start_sample > min(maximum, plausible):
                continue
            if _removed(word.start_sample, word.end_sample, removed_spans):
                continue
            words.append((word.start_sample, word.end_sample))
    return words


def _contained(
    word: tuple[int, int],
    spans: Sequence[tuple[int, int]],
    tolerance: int,
) -> bool:
    start, end = word
    return any(
        span_start - tolerance <= start and end <= span_end + tolerance
        for span_start, span_end in spans
    )


def enforce_word_integrity(
    spans: Sequence[tuple[int, int]],
    transcript: Sequence[Any],
    discard_ids: set[int],
    *,
    removed_spans: Sequence[tuple[int, int]] = (),
    sample_rate: int = 48_000,
    max_word_ms: int = 1500,
    max_gap_ms: int = 500,
    tolerance_ms: int = 5,
) -> tuple[list[tuple[int, int]], list[dict[str, int]]]:
    """Merge split spans so every kept word is whole; report what cannot be fixed."""

    words = _kept_words(
        transcript,
        discard_ids,
        removed_spans,
        max_word_ms=max_word_ms,
        sample_rate=sample_rate,
    )
    if not words:
        return merge_spans(spans), []
    tolerance = round(tolerance_ms * sample_rate / 1000)
    maximum_gap = round(max_gap_ms * sample_rate / 1000)
    current = merge_spans(spans)
    violations: list[dict[str, int]] = []
    for word_start, word_end in words:
        if _contained((word_start, word_end), current, tolerance):
            continue
        overlapping = [
            index
            for index, (start, end) in enumerate(current)
            if start < word_end and end > word_start
        ]
        if not overlapping:
            violations.append(
                {
                    "word_start": word_start,
                    "word_end": word_end,
                    "reason": 0,
                }
            )
            continue
        pieces = [current[index] for index in overlapping]
        pieces.sort()
        internal_gap = sum(
            max(0, right[0] - left[1])
            for left, right in zip(pieces, pieces[1:], strict=False)
        )
        low = min(min(piece[0] for piece in pieces), word_start)
        high = max(max(piece[1] for piece in pieces), word_end)
        if internal_gap > maximum_gap or (high - low) - (word_end - word_start) > maximum_gap:
            violations.append(
                {
                    "word_start": word_start,
                    "word_end": word_end,
                    "reason": 1,
                }
            )
            continue
        keep = [span for index, span in enumerate(current) if index not in overlapping]
        keep.append((low, high))
        current = merge_spans(keep)
    return current, violations
