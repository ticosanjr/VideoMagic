"""Transcript cleanup: low-confidence marking and immediate repetition removal."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from videoflow.domain.state import Sentence, WordTiming

_LOW_CONFIDENCE = 0.20
_DUPLICATE_CONFIDENCE = 0.35
_DUPLICATE_GAP_SEC = 0.20


def _normalise(token: str) -> str:
    return re.sub(r"[^0-9a-zà-ÿ]+", "", token.casefold())


def clean_transcript(
    sentences: Sequence[Sentence],
    *,
    sample_rate: int,
) -> tuple[list[Sentence], dict[str, Any]]:
    marked = 0
    removed = 0
    result: list[Sentence] = []
    for sentence in sentences:
        words: list[WordTiming] = []
        for word in sentence.words:
            low = word.probability < _LOW_CONFIDENCE
            marked += 1 if low else 0
            item = word.model_copy(update={"low_confidence": low})
            norm = _normalise(item.word)
            if words and norm and _normalise(words[-1].word) == norm:
                gap = item.start_sample - words[-1].end_sample
                if (
                    gap >= 0
                    and gap <= round(_DUPLICATE_GAP_SEC * sample_rate)
                    and item.probability < _DUPLICATE_CONFIDENCE
                ):
                    removed += 1
                    continue
            words.append(item)
        text = " ".join(word.word for word in words).strip() or sentence.text
        result.append(sentence.model_copy(update={"words": words, "text": text}))
    return result, {
        "low_confidence_words": marked,
        "removed_repetitions": removed,
        "sentences": len(result),
    }


__all__ = ["clean_transcript"]
