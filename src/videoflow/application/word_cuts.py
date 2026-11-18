"""Deterministic word-level cuts for stutters, retakes, and local repeats.

The sentence-level LLM groups whole retakes, but many human cuts happen inside a
sentence: a repeated word, a restarted prefix, or a suffix that is repeated at
the start of the next sentence. This module finds those cases on the word
stream, keeps the last complete occurrence, and cuts only duplicated words.
Unique words and numbers are protected.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from difflib import SequenceMatcher

from videoflow.application.text import (
    STOPWORDS as _STOPWORDS,
)
from videoflow.application.text import (
    URL_PATTERN as _URL,
)
from videoflow.domain.state import Sentence

_TOKEN = re.compile(r"[^a-z0-9à-ÿ]+")
_NUMBER = re.compile(r"\d")


_FILLERS = {
    "ah",
    "ahn",
    "eh",
    "er",
    "erm",
    "ha",
    "hã",
    "hm",
    "hmm",
    "hum",
    "uh",
    "um",
    "é",
    "ne",
    "né",
    "tipo",
    "entao",
    "então",
}

_PRIORITY = {
    "filler": 0,
    "stutter": 0,
    "prefix_tail": 1,
    "restatement": 2,
    "ngram": 3,
}


def _normalise(text: str) -> str:
    return _TOKEN.sub("", text.casefold())


def _protected(text: str) -> bool:
    return bool(_NUMBER.search(text) or _URL.search(text))


def _content(norm: str) -> bool:
    return bool(norm) and norm not in _STOPWORDS and (
        len(norm) >= 3 or norm.isdigit()
    )


@dataclass(frozen=True, slots=True)
class WordRef:
    index: int
    sentence_id: int
    start_sample: int
    end_sample: int
    text: str
    norm: str
    protected: bool
    low_confidence: bool = False


@dataclass(frozen=True, slots=True)
class WordCut:
    start: int
    end: int
    reason: str
    text: str


@dataclass(frozen=True, slots=True)
class WordCutPlan:
    cuts: list[tuple[int, int]]
    report: list[dict[str, object]]
    cut_words: int
    total_words: int

    def to_dict(self) -> dict[str, object]:
        return {
            "cuts": self.report,
            "cut_words": self.cut_words,
            "total_words": self.total_words,
            "ratio": round(
                self.cut_words / max(1, self.total_words), 6
            ),
        }


def _flatten(
    transcript: Sequence[Sentence],
    discard_ids: set[int],
) -> list[WordRef]:
    words: list[WordRef] = []
    for sentence in sorted(transcript, key=lambda item: (item.start_sample, item.id)):
        if sentence.id in discard_ids:
            continue
        for word in sentence.words:
            norm = _normalise(word.word)
            if not norm or word.low_confidence:
                continue
            words.append(
                WordRef(
                    index=len(words),
                    sentence_id=sentence.id,
                    start_sample=word.start_sample,
                    end_sample=word.end_sample,
                    text=word.word,
                    norm=norm,
                    protected=_protected(word.word),
                    low_confidence=word.low_confidence,
                )
            )
    words.sort(key=lambda item: (item.start_sample, item.end_sample))
    return [replace(word, index=index) for index, word in enumerate(words)]


def _sentence_groups(words: Sequence[WordRef]) -> list[list[WordRef]]:
    groups: dict[int, list[WordRef]] = {}
    for word in words:
        groups.setdefault(word.sentence_id, []).append(word)
    ordered = sorted(groups.values(), key=lambda group: group[0].start_sample)
    return [sorted(group, key=lambda item: item.index) for group in ordered]


def _stutter_cuts(
    words: Sequence[WordRef],
    *,
    sample_rate: int,
    max_gap_ms: int = 900,
) -> list[WordCut]:
    gap = round(max_gap_ms * sample_rate / 1000)
    short_gap = round(350 * sample_rate / 1000)
    cuts: list[WordCut] = []
    index = 0
    while index < len(words) - 1:
        following = index + 1
        while following < len(words) and words[following].norm == words[index].norm:
            same_sentence = words[following].sentence_id == words[index].sentence_id
            allowed = gap if same_sentence else short_gap
            if words[following].start_sample - words[following - 1].end_sample > allowed:
                break
            following += 1
        if following - index >= 2:
            cuts.append(
                WordCut(
                    index,
                    following - 2,
                    "stutter",
                    " ".join(word.text for word in words[index:following]),
                )
            )
        index = following
    return cuts


def _filler_cuts(words: Sequence[WordRef]) -> list[WordCut]:
    cuts: list[WordCut] = []
    for index, word in enumerate(words):
        if word.norm not in _FILLERS or _protected(word.text):
            continue
        cuts.append(WordCut(index, index, "filler", word.text))
    return cuts


def _phrase_stutters(
    words: Sequence[WordRef],
    *,
    sample_rate: int,
    max_gap_ms: int = 700,
) -> list[WordCut]:
    gap = round(max_gap_ms * sample_rate / 1000)
    cuts: list[WordCut] = []
    for size in (2, 3):
        index = 0
        while index + 2 * size <= len(words):
            first = [word.norm for word in words[index : index + size]]
            second = [word.norm for word in words[index + size : index + 2 * size]]
            same_sentence = (
                words[index].sentence_id == words[index + 2 * size - 1].sentence_id
            )
            separated = (
                words[index + size].start_sample
                - words[index + size - 1].end_sample
            )
            if first == second and same_sentence and separated <= gap:
                cuts.append(
                    WordCut(
                        index,
                        index + size - 1,
                        "stutter",
                        " ".join(
                            word.text for word in words[index : index + size]
                        ),
                    )
                )
                index += 2 * size
            else:
                index += 1
    return cuts


def _sentence_cuts(
    groups: Sequence[Sequence[WordRef]],
    *,
    window: int = 4,
) -> list[WordCut]:
    cuts: list[WordCut] = []
    for left_index, left in enumerate(groups):
        if len(left) < 2:
            continue
        left_norms = [word.norm for word in left]
        for right_index in range(left_index + 1, min(len(groups), left_index + window + 1)):
            right = groups[right_index]
            if len(right) < 2:
                continue
            right_norms = [word.norm for word in right]
            matcher = SequenceMatcher(None, left_norms, right_norms, autojunk=False)
            ratio = matcher.ratio()
            for block in matcher.get_matching_blocks():
                if block.size < 3:
                    continue
                block_tokens = left_norms[block.a : block.a + block.size]
                if not any(_content(token) for token in block_tokens):
                    continue
                at_left_start = block.a == 0
                at_left_end = block.a + block.size == len(left_norms)
                at_right_start = block.b == 0
                at_right_end = block.b + block.size == len(right_norms)
                boundary = (
                    (at_left_end and at_right_start)
                    or (at_left_start and at_right_start)
                    or (at_left_end and at_right_end)
                )
                if not boundary and ratio < 0.8:
                    continue
                if not boundary and block.size < 4:
                    continue
                reason = "prefix_tail" if boundary else "restatement"
                cuts.append(
                    WordCut(
                        left[block.a].index,
                        left[block.a + block.size - 1].index,
                        reason,
                        " ".join(word.text for word in left[block.a : block.a + block.size]),
                    )
                )
    return cuts


def _ngram_cuts(
    words: Sequence[WordRef],
    *,
    sample_rate: int,
    min_words: int = 4,
    max_words: int = 8,
    max_gap_seconds: float = 120.0,
) -> list[WordCut]:
    gap = round(max_gap_seconds * sample_rate)
    cuts: list[WordCut] = []
    for size in range(max(4, min_words), max_words + 1):
        positions: dict[tuple[str, ...], list[int]] = defaultdict(list)
        for start in range(0, len(words) - size + 1):
            gram = tuple(word.norm for word in words[start : start + size])
            if not any(_content(token) for token in gram):
                continue
            positions[gram].append(start)
        for _gram, starts in positions.items():
            if len(starts) < 2:
                continue
            ordered = sorted(set(starts))
            last = ordered[-1]
            for start in ordered[:-1]:
                if words[last].start_sample - words[start].start_sample > gap:
                    continue
                if start + size > last:
                    continue
                cuts.append(
                    WordCut(
                        start,
                        start + size - 1,
                        "ngram",
                        " ".join(word.text for word in words[start : start + size]),
                    )
                )
    return cuts


def _split_cut(
    cut: WordCut,
    words: Sequence[WordRef],
    counts: Counter[str],
) -> list[WordCut]:
    runs: list[WordCut] = []
    current_start: int | None = None
    for index in range(cut.start, cut.end + 1):
        word = words[index]
        cuttable = counts[word.norm] > 1 or cut.reason == "filler"
        if cuttable:
            if current_start is None:
                current_start = index
        elif current_start is not None:
            runs.append(
                WordCut(
                    current_start,
                    index - 1,
                    cut.reason,
                    " ".join(item.text for item in words[current_start:index]),
                )
            )
            current_start = None
    if current_start is not None:
        runs.append(
            WordCut(
                current_start,
                cut.end,
                cut.reason,
                " ".join(item.text for item in words[current_start : cut.end + 1]),
            )
        )
    return [
        run
        for run in runs
        if run.reason == "filler"
        or any(_content(words[index].norm) for index in range(run.start, run.end + 1))
    ]


def _merge(cuts: Sequence[WordCut]) -> list[WordCut]:
    ordered = sorted(cuts, key=lambda item: (item.start, item.end))
    merged: list[WordCut] = []
    for cut in ordered:
        if merged and cut.start <= merged[-1].end:
            previous = merged[-1]
            merged[-1] = WordCut(
                previous.start,
                max(previous.end, cut.end),
                previous.reason
                if _PRIORITY[previous.reason] <= _PRIORITY[cut.reason]
                else cut.reason,
                previous.text if len(previous.text) >= len(cut.text) else cut.text,
            )
        else:
            merged.append(cut)
    return merged


def plan_word_cuts(
    transcript: Sequence[Sentence],
    discard_ids: set[int],
    *,
    sample_rate: int = 48_000,
    max_gap_seconds: float = 120.0,
    min_words: int = 4,
    max_cut_ratio: float = 0.2,
    max_cuts: int = 60,
    remove_fillers: bool = False,
) -> WordCutPlan:
    """Return word-level source cuts and a report."""

    words = _flatten(transcript, discard_ids)
    total = len(words)
    if total < 2:
        return WordCutPlan([], [], 0, total)
    counts = Counter(word.norm for word in words)
    candidates: list[WordCut] = []
    if remove_fillers:
        candidates.extend(_filler_cuts(words))
    candidates.extend(_stutter_cuts(words, sample_rate=sample_rate))
    candidates.extend(_phrase_stutters(words, sample_rate=sample_rate))
    candidates.extend(_sentence_cuts(_sentence_groups(words)))
    candidates.extend(
        _ngram_cuts(
            words,
            sample_rate=sample_rate,
            min_words=min_words,
            max_gap_seconds=max_gap_seconds,
        )
    )
    expanded: list[WordCut] = []
    for candidate in candidates:
        expanded.extend(_split_cut(candidate, words, counts))
    merged = _merge(expanded)
    limit = max(1, math.floor(total * max_cut_ratio))
    selected: list[WordCut] = []
    used = 0
    for cut in sorted(
        merged,
        key=lambda item: (
            _PRIORITY[item.reason],
            -(item.end - item.start + 1),
            item.start,
        ),
    ):
        length = cut.end - cut.start + 1
        if used + length > limit and cut.reason not in {"stutter", "filler"}:
            continue
        if any(
            cut.start <= existing.end and existing.start <= cut.end
            for existing in selected
        ):
            continue
        selected.append(cut)
        used += length
        if len(selected) >= max_cuts:
            break
    selected.sort(key=lambda item: item.start)
    spans: list[tuple[int, int]] = []
    report: list[dict[str, object]] = []
    for cut in selected:
        start = words[cut.start].start_sample
        end = words[cut.end].end_sample
        spans.append((start, end))
        report.append(
            {
                "start_sec": round(start / sample_rate, 3),
                "end_sec": round(end / sample_rate, 3),
                "reason": cut.reason,
                "text": cut.text,
                "words": cut.end - cut.start + 1,
            }
        )
    merged_spans: list[tuple[int, int]] = []
    for start, end in spans:
        if merged_spans and start <= merged_spans[-1][1]:
            merged_spans[-1] = (merged_spans[-1][0], max(merged_spans[-1][1], end))
        else:
            merged_spans.append((start, end))
    return WordCutPlan(
        cuts=merged_spans,
        report=report,
        cut_words=used,
        total_words=total,
    )
