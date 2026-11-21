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
from dataclasses import dataclass
from difflib import SequenceMatcher

from videoflow.application.repetition import (
    RepeatWord,
    detect_words,
    word_stream,
)
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
    "phrase": 0,
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
    """Flatten the kept transcript without losing low-confidence words.

    Dropping a low-confidence word makes its neighbours look adjacent and can
    create a false repetition. The word stays in the stream, marked, and the
    repetition detector refuses to cut it.
    """

    words: list[WordRef] = [
        WordRef(
            index=token.index,
            sentence_id=token.sentence_id,
            start_sample=token.start_sample,
            end_sample=token.end_sample,
            text=token.text,
            norm=token.norm,
            protected=token.protected,
            low_confidence=token.low_confidence,
        )
        for token in word_stream(transcript, discard_ids)
    ]
    return words


def _sentence_groups(words: Sequence[WordRef]) -> list[list[WordRef]]:
    groups: dict[int, list[WordRef]] = {}
    for word in words:
        groups.setdefault(word.sentence_id, []).append(word)
    ordered = sorted(groups.values(), key=lambda group: group[0].start_sample)
    return [sorted(group, key=lambda item: item.index) for group in ordered]


def _repetition_cuts(
    words: Sequence[WordRef],
    *,
    sample_rate: int,
    max_gap_sec: float = 1.2,
) -> list[WordCut]:
    """Immediate word and phrase repetitions, including short stopwords."""

    tokens = [
        RepeatWord(
            index=word.index,
            sentence_id=word.sentence_id,
            text=word.text,
            norm=word.norm,
            start_sample=word.start_sample,
            end_sample=word.end_sample,
            low_confidence=word.low_confidence,
            protected=word.protected,
        )
        for word in words
    ]
    plan = detect_words(tokens, sample_rate=sample_rate, max_gap_sec=max_gap_sec)
    return [
        WordCut(
            cut.first_index,
            cut.last_index,
            cut.reason,
            cut.text,
        )
        for cut in plan.cuts
    ]


def _filler_cuts(words: Sequence[WordRef]) -> list[WordCut]:
    cuts: list[WordCut] = []
    for index, word in enumerate(words):
        if word.norm not in _FILLERS or _protected(word.text):
            continue
        cuts.append(WordCut(index, index, "filler", word.text))
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
        cuttable = (
            (counts[word.norm] > 1 or cut.reason == "filler")
            and not word.protected
            and not word.low_confidence
        )
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
        if run.reason in {"filler", "stutter", "phrase"}
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
    max_cut_ratio: float = 0.9,
    remove_fillers: bool = False,
    repeat_gap_seconds: float = 1.2,
) -> WordCutPlan:
    """Return word-level source cuts and a report.

    There is no count limit: every detected repetition is cut, because a
    silent cap makes the last repeated words survive in long recordings.
    ``max_cut_ratio`` (default 0.9) is only a catastrophic-removal safety
    ceiling, not a per-run cut count.
    """

    words = _flatten(transcript, discard_ids)
    total = len(words)
    if total < 2:
        return WordCutPlan([], [], 0, total)
    counts = Counter(word.norm for word in words)
    candidates: list[WordCut] = []
    if remove_fillers:
        candidates.extend(_filler_cuts(words))
    candidates.extend(
        _repetition_cuts(
            words,
            sample_rate=sample_rate,
            max_gap_sec=repeat_gap_seconds,
        )
    )
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
    limit = max(1, math.floor(total * max_cut_ratio))
    selected: list[WordCut] = []
    used = 0
    # Selection runs on the raw candidates: a large overlapping n-gram must not
    # merge away the small stutters before they get a chance to be chosen.
    for cut in sorted(
        expanded,
        key=lambda item: (
            _PRIORITY[item.reason],
            -(item.end - item.start + 1),
            item.start,
        ),
    ):
        length = cut.end - cut.start + 1
        if used + length > limit:
            continue
        if any(
            cut.start <= existing.end and existing.start <= cut.end
            for existing in selected
        ):
            continue
        selected.append(cut)
        used += length
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
