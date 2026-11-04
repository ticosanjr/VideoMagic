"""Normalise overlapping ASR segments into clean utterances.

Whisper often emits sliding windows: a segment may start with the tail of the
previous sentence and then repeat the passage from its beginning. Retake
grouping needs complete sentences, so we merge the word streams, remove the
duplicate overlap, and split on punctuation or long pauses.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from videoflow.domain.state import Sentence, WordTiming

_SENTENCE_END = re.compile(r"[.!?…]$")
_TOKEN = re.compile(r"[^\wÀ-ÿ]+", re.UNICODE)
_PUNCTUATION_PREFIX = ".,!?;:%)]}"
_OPEN_ENDINGS = ("(", "[", "{", "-", "/", "—")


def _normal(word: str) -> str:
    return _TOKEN.sub("", word.casefold())


def _pseudo_words(sentence: Sentence) -> list[WordTiming]:
    tokens = sentence.text.split()
    if not tokens:
        return []
    count = max(1, len(tokens))
    span = max(1, sentence.end_sample - sentence.start_sample)
    output: list[WordTiming] = []
    for index, token in enumerate(tokens):
        start = sentence.start_sample + round(span * index / count)
        end = sentence.start_sample + round(span * (index + 1) / count)
        output.append(
            WordTiming(
                word=token,
                start_sample=start,
                end_sample=max(start + 1, end),
                probability=0.5,
            )
        )
    return output


def _flatten(
    sentences: Sequence[Sentence],
    *,
    sample_rate: int = 48000,
    overlap_gap_seconds: float = 0.25,
) -> list[WordTiming]:
    merged: list[WordTiming] = []
    previous_end: int | None = None
    for sentence in sorted(sentences, key=lambda item: (item.start_sample, item.id)):
        words = list(sentence.words) or _pseudo_words(sentence)
        words = [word for word in words if word.word.strip()]
        if not words:
            continue
        if (
            not merged
            or previous_end is None
            or (sentence.start_sample - previous_end) / sample_rate
            > overlap_gap_seconds
        ):
            merged.extend(words)
            previous_end = sentence.end_sample
            continue
        limit = min(len(merged), len(words), 40)
        overlap = 0
        for size in range(limit, 0, -1):
            if [_normal(word.word) for word in merged[-size:]] == [
                _normal(word.word) for word in words[:size]
            ]:
                overlap = size
                break
        for index in range(overlap):
            existing = merged[-overlap + index]
            incoming = words[index]
            if _SENTENCE_END.search(incoming.word) and not _SENTENCE_END.search(
                existing.word
            ):
                merged[-overlap + index] = existing.model_copy(
                    update={"word": incoming.word}
                )
        merged.extend(words[overlap:])
        previous_end = max(previous_end, sentence.end_sample)
    return merged


def _join(words: Sequence[WordTiming]) -> str:
    text = ""
    for word in words:
        token = word.word.strip()
        if not token:
            continue
        if not text:
            text = token
        elif (
            token.startswith(tuple(_PUNCTUATION_PREFIX))
            or token in {"%", "..."}
            or text.endswith(_OPEN_ENDINGS)
        ):
            text += token
        else:
            text += " " + token
    return text.strip()


def normalize_transcript(
    sentences: Sequence[Sentence],
    *,
    sample_rate: int = 48000,
    pause_seconds: float = 1.2,
) -> list[Sentence]:
    """Return complete, non-overlapping sentences with word timings."""

    merged = _flatten(sentences, sample_rate=sample_rate)
    if not merged:
        return []
    minimum_words = 4
    output: list[Sentence] = []
    current: list[WordTiming] = []
    for index, word in enumerate(merged):
        current.append(word)
        next_gap = 0.0
        next_word = ""
        if index + 1 < len(merged):
            next_gap = (
                merged[index + 1].start_sample - word.end_sample
            ) / sample_rate
            next_word = merged[index + 1].word.lstrip("\"'“‘([ ")
        ends = bool(_SENTENCE_END.search(word.word))
        pauses = (
            next_gap >= pause_seconds
            and len(current) >= minimum_words
            and bool(next_word[:1].isupper())
        )
        if not ends and not pauses:
            continue
        text = _join(current)
        if text:
            output.append(
                Sentence(
                    id=len(output),
                    start_sample=current[0].start_sample,
                    end_sample=current[-1].end_sample,
                    text=text,
                    words=list(current),
                )
            )
        current = []
    if current:
        text = _join(current)
        if text:
            output.append(
                Sentence(
                    id=len(output),
                    start_sample=current[0].start_sample,
                    end_sample=current[-1].end_sample,
                    text=text,
                    words=list(current),
                )
            )
    return output
