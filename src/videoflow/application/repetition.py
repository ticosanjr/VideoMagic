"""Deterministic repetition detection over the whole word stream.

The transcript is split into sentences and ASUs, but a repeated word often
crosses those boundaries: a pause before the retry, a comma, or a sentence
break. This module works on the flat word stream so the decision does not
depend on where the ASR happened to segment the text.

Rules:

* a run of identical words (1..N) with a short gap is a stutter; the earlier
  occurrences are cut and the last fluent occurrence is kept;
* an immediately repeated phrase (2..4 words) is treated the same way;
* short words and stopwords are included, because "eu eu" and "que que" are the
  most common false starts and the old content-word filter skipped them;
* ambiguous cases are never cut here: strong punctuation between the
  occurrences ("não, não"), low-confidence words, numbers and URLs are returned
  as review candidates for the semantic LLM pass.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from videoflow.domain.state import Sentence

_TOKEN = re.compile(r"[^0-9a-zà-ÿ]+")
_NUMBER = re.compile(r"\d")
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
_STRONG_END = re.compile(r"[.!?…:;]\s*$")
_SOFT_END = re.compile(r",\s*$")

# Short words that are often repeated for emphasis ("não... não"). A tight
# repetition is a stutter; a longer one is rhetorical and goes to the LLM.
_EMPHASIS = frozenset(
    {
        "nao",
        "não",
        "sim",
        "muito",
        "muita",
        "nunca",
        "sempre",
        "tudo",
        "nada",
    }
)
_EMPHASIS_GAP_SEC = 0.35


@dataclass(frozen=True, slots=True)
class RepeatWord:
    index: int
    sentence_id: int
    text: str
    norm: str
    start_sample: int
    end_sample: int
    probability: float = 1.0
    low_confidence: bool = False
    protected: bool = False


@dataclass(frozen=True, slots=True)
class RepetitionCut:
    first_index: int
    last_index: int
    keeper_index: int
    reason: str
    text: str
    confidence: float
    ambiguous: bool = False


@dataclass(frozen=True, slots=True)
class RepetitionPlan:
    cuts: list[RepetitionCut]
    ambiguous: list[RepetitionCut]

    def to_dict(self) -> dict[str, object]:
        return {
            "cuts": len(self.cuts),
            "ambiguous": len(self.ambiguous),
            "details": [
                {
                    "reason": cut.reason,
                    "text": cut.text,
                    "confidence": cut.confidence,
                }
                for cut in self.cuts
            ],
            "review": [
                {
                    "reason": cut.reason,
                    "text": cut.text,
                    "confidence": cut.confidence,
                }
                for cut in self.ambiguous
            ],
        }


def normalise_token(text: str) -> str:
    return _TOKEN.sub("", text.casefold())


def _protected(text: str) -> bool:
    return bool(_NUMBER.search(text) or _URL.search(text))


def word_stream(
    transcript: Sequence[Sentence],
    discard_ids: set[int] | None = None,
) -> list[RepeatWord]:
    """Flatten kept sentences into start-ordered word tokens."""

    discarded = discard_ids or set()
    words: list[RepeatWord] = []
    for sentence in transcript:
        if sentence.id in discarded:
            continue
        for word in sentence.words:
            norm = normalise_token(word.word)
            if not norm:
                continue
            words.append(
                RepeatWord(
                    index=0,
                    sentence_id=sentence.id,
                    text=word.word,
                    norm=norm,
                    start_sample=word.start_sample,
                    end_sample=word.end_sample,
                    probability=float(word.probability),
                    low_confidence=bool(word.low_confidence),
                    protected=_protected(word.word),
                )
            )
    words.sort(key=lambda item: (item.start_sample, item.end_sample))
    return [
        RepeatWord(
            index=position,
            sentence_id=word.sentence_id,
            text=word.text,
            norm=word.norm,
            start_sample=word.start_sample,
            end_sample=word.end_sample,
            probability=word.probability,
            low_confidence=word.low_confidence,
            protected=word.protected,
        )
        for position, word in enumerate(words)
    ]


def _punctuated(text: str) -> bool:
    return bool(_STRONG_END.search(text) or _SOFT_END.search(text))


def _is_ambiguous(words: Sequence[RepeatWord]) -> bool:
    return any(
        word.low_confidence or word.protected or _punctuated(word.text)
        for word in words[:-1]
    )


def _confidence(removed: Sequence[RepeatWord]) -> float:
    if not removed:
        return 1.0
    average = sum(word.probability for word in removed) / len(removed)
    if average < 0.5:
        return 0.5
    if any(word.probability < 0.7 for word in removed):
        return 0.75
    return 0.95


def _gap(left: RepeatWord, right: RepeatWord) -> int:
    return right.start_sample - left.end_sample


def detect_words(
    words: Sequence[RepeatWord],
    *,
    max_gap_sec: float = 1.2,
    sample_rate: int = 48_000,
    max_phrase_words: int = 4,
) -> RepetitionPlan:
    """Find immediate word and phrase repetitions in a flat token stream."""

    limit = max(0, round(max_gap_sec * sample_rate))
    cuts: list[RepetitionCut] = []
    ambiguous: list[RepetitionCut] = []
    consumed: set[int] = set()

    def record(first: int, last: int, keeper: int, reason: str) -> None:
        removed = list(words[first : last + 1])
        text = " ".join(word.text for word in words[first : keeper + 1])
        is_ambiguous = _is_ambiguous(list(words[first : keeper + 1]))
        if (
            not is_ambiguous
            and reason == "stutter"
            and words[keeper].norm in _EMPHASIS
        ):
            gap = words[keeper].start_sample - words[keeper - 1].end_sample
            if gap > round(_EMPHASIS_GAP_SEC * sample_rate):
                is_ambiguous = True
        cut = RepetitionCut(
            first_index=first,
            last_index=last,
            keeper_index=keeper,
            reason=reason,
            text=text,
            confidence=_confidence(removed),
            ambiguous=is_ambiguous,
        )
        (ambiguous if cut.ambiguous else cuts).append(cut)

    total = len(words)
    index = 0
    while index < total - 1:
        # A run of the same word, e.g. "eu eu eu".
        run_end = index
        while run_end + 1 < total:
            following = words[run_end + 1]
            if following.norm != words[index].norm:
                break
            if _gap(words[run_end], following) > limit:
                break
            run_end += 1
        if run_end > index:
            record(index, run_end - 1, run_end, "stutter")
            consumed.update(range(index, run_end))
            index = run_end + 1
        else:
            index += 1

    # Phrase pass. A word already removed by a stutter cannot be part of a
    # phrase cut; otherwise overlapping n-grams ("nova casa casa") swallow the
    # whole stream.
    index = 0
    while index < total:
        if index in consumed:
            index += 1
            continue
        matched = False
        for size in range(2, max_phrase_words + 1):
            end = index + 2 * size
            if end > total:
                break
            if any(position in consumed for position in range(index, end)):
                continue
            first = [word.norm for word in words[index : index + size]]
            second = [word.norm for word in words[index + size : end]]
            if first != second:
                continue
            if _gap(words[index + size - 1], words[index + size]) > limit:
                continue
            record(index, index + size - 1, index + size, "phrase")
            consumed.update(range(index, index + size))
            index = end
            matched = True
            break
        if matched:
            continue
        index += 1
    cuts.sort(key=lambda item: item.first_index)
    ambiguous.sort(key=lambda item: item.first_index)
    return RepetitionPlan(cuts=cuts, ambiguous=ambiguous)


def detect_repetitions(
    transcript: Sequence[Sentence],
    discard_ids: set[int] | None = None,
    *,
    sample_rate: int = 48_000,
    max_gap_sec: float = 1.2,
    max_phrase_words: int = 4,
) -> RepetitionPlan:
    """Convenience wrapper for sentence transcripts."""

    return detect_words(
        word_stream(transcript, discard_ids),
        sample_rate=sample_rate,
        max_gap_sec=max_gap_sec,
        max_phrase_words=max_phrase_words,
    )


__all__ = [
    "RepeatWord",
    "RepetitionCut",
    "RepetitionPlan",
    "detect_repetitions",
    "detect_words",
    "normalise_token",
    "word_stream",
]
