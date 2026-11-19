"""Short thought-boundary selection.

A Short must end after a complete idea, not at the duration target or in the
middle of a clause. This module extends or retracts the end within a small
window until it lands on terminal punctuation followed by a real pause.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from videoflow.domain.state import Sentence

__all__ = ["BoundaryResult", "enforce_thought_boundary"]

_TERMINAL = re.compile(r"[.!?…]\s*$")
_DANGLING = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "entre",
    "mas",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "pela",
    "pelas",
    "pelo",
    "pelos",
    "por",
    "que",
    "se",
    "sem",
    "sobre",
    "um",
    "uma",
    "and",
    "at",
    "but",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


@dataclass(frozen=True, slots=True)
class BoundaryResult:
    start_sample: int
    end_sample: int
    adjusted: bool
    reason: str
    boundary_sentence_id: int | None = None


def _is_terminal(sentence: Sentence) -> bool:
    text = sentence.text.strip()
    if not text or not _TERMINAL.search(text):
        return False
    words = re.findall(r"[A-Za-zÀ-ÿ0-9]+", text.casefold())
    return bool(words) and words[-1] not in _DANGLING


def _pause_after(
    sentence: Sentence,
    sentences: Sequence[Sentence],
    *,
    min_pause_ms: int,
    sample_rate: int,
) -> bool:
    later = next(
        (item for item in sentences if item.start_sample >= sentence.end_sample),
        None,
    )
    if later is None:
        return True
    return later.start_sample - sentence.end_sample >= (
        min_pause_ms * max(1, sample_rate) // 1000
    )


def enforce_thought_boundary(
    sentences: Sequence[Sentence],
    start_sample: int,
    end_sample: int,
    *,
    sample_rate: int = 48_000,
    max_adjust_sec: float = 4.0,
    min_pause_ms: int = 250,
) -> BoundaryResult:
    """Move a Short end to the nearest complete thought within ±max_adjust_sec."""

    ordered = sorted(sentences, key=lambda item: (item.start_sample, item.id))
    start = max(0, int(start_sample))
    end = max(start + 1, int(end_sample))
    if not ordered:
        return BoundaryResult(start, end, False, "no transcript")
    window = max(0, round(max(1.0, max_adjust_sec) * sample_rate))
    minimum = max(1, round(0.5 * sample_rate))
    candidates = [
        sentence
        for sentence in ordered
        if _is_terminal(sentence)
        and _pause_after(
            sentence,
            ordered,
            min_pause_ms=min_pause_ms,
            sample_rate=sample_rate,
        )
        and start + minimum <= sentence.end_sample <= end + window
        and sentence.end_sample >= end - window
    ]
    if candidates:
        chosen = min(candidates, key=lambda item: (abs(item.end_sample - end), item.end_sample))
        if chosen.end_sample == end:
            return BoundaryResult(start, end, False, "already complete", chosen.id)
        return BoundaryResult(
            start,
            chosen.end_sample,
            True,
            "extended to the nearest complete thought"
            if chosen.end_sample > end
            else "retracted to the nearest complete thought",
            chosen.id,
        )
    return BoundaryResult(start, end, False, "no complete thought within the window")
