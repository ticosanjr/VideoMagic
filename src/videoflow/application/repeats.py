"""Deterministic repeated-passage cuts.

The LLM groups retakes semantically, but exact short passages can still slip
through. This pass keeps the last occurrence of a repeated n-gram and removes
only the earlier occurrences, preserving any unique content between them.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from videoflow.domain.state import Sentence


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9à-ÿ]+", "", text.casefold())


def detect_repeated_cuts(
    transcript: Sequence[Sentence],
    discard_ids: set[int],
    *,
    sample_rate: int = 48_000,
    min_words: int = 5,
    max_gap_seconds: float = 180.0,
    pad_ms: int = 40,
    max_cuts: int = 40,
) -> tuple[list[tuple[int, int]], list[dict[str, object]]]:
    """Return source cuts for earlier occurrences of exact repeated passages."""

    words: list[tuple[int, int, str, str, int]] = []
    for sentence in sorted(transcript, key=lambda item: (item.start_sample, item.id)):
        if sentence.id in discard_ids:
            continue
        for word in sentence.words:
            token = _normal(word.word)
            if token:
                words.append(
                    (word.start_sample, word.end_sample, token, word.word, sentence.id)
                )
    words.sort(key=lambda item: (item[0], item[1]))
    if len(words) < min_words + 1:
        return [], []
    width = max(2, int(min_words))
    occurrences: dict[tuple[str, ...], list[tuple[int, int]]] = {}
    for index in range(len(words) - width + 1):
        gram = tuple(item[2] for item in words[index : index + width])
        occurrences.setdefault(gram, []).append((index, index + width - 1))
    pad = max(0, round(pad_ms * sample_rate / 1000))
    raw_cuts: list[tuple[int, int]] = []
    report: list[dict[str, object]] = []
    for _gram, items in occurrences.items():
        if len(items) < 2:
            continue
        items = sorted(set(items))
        last_start, last_end = items[-1]
        if words[last_end][1] - words[items[0][0]][0] > max_gap_seconds * sample_rate:
            continue
        text = " ".join(
            words[index][3] for index in range(items[0][0], items[0][1] + 1)
        )
        for start_index, end_index in items[:-1]:
            if end_index >= last_start:
                continue
            start = max(0, words[start_index][0] - pad)
            end = words[end_index][1] + pad
            if start_index > 0:
                start = max(start, words[start_index - 1][1])
            if end_index + 1 < len(words):
                end = min(end, words[end_index + 1][0])
            if end <= start:
                continue
            raw_cuts.append((start, end))
            report.append(
                {
                    "text": text,
                    "start_sec": round(start / sample_rate, 3),
                    "end_sec": round(end / sample_rate, 3),
                }
            )
            if len(raw_cuts) >= max_cuts:
                break
        if len(raw_cuts) >= max_cuts:
            break
    raw_cuts.sort()
    merged: list[tuple[int, int]] = []
    for start, end in raw_cuts:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged, report[:max_cuts]
