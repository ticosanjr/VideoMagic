"""Take-level retake detection.

A human editor chooses between whole *takes*, not between isolated sentences.
This module segments consecutive sentences into takes, groups near-duplicate
takes, and selects a keeper with hard content-preservation rules. It is
deterministic: the LLM can still break semantic ties elsewhere, but the take
decision is reproducible.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from videoflow.application.text import content_tokens, normalize_text, token_list, token_set
from videoflow.domain.state import Sentence

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
_STOPWORDS = {
    "a",
    "o",
    "as",
    "os",
    "e",
    "é",
    "de",
    "da",
    "do",
    "das",
    "dos",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "um",
    "uma",
    "uns",
    "umas",
    "que",
    "se",
    "por",
    "para",
    "com",
    "sem",
    "ao",
    "aos",
    "à",
    "às",
    "mais",
    "menos",
    "mas",
    "ou",
    "como",
    "quando",
    "porque",
    "então",
    "entao",
    "aí",
    "ai",
    "aqui",
    "agora",
    "já",
    "ja",
    "ainda",
    "também",
    "tambem",
    "só",
    "so",
    "não",
    "nao",
    "sim",
    "isso",
    "isto",
    "ele",
    "ela",
    "eles",
    "elas",
    "eu",
    "nós",
    "você",
    "voce",
    "tem",
    "foi",
    "vai",
    "ser",
    "são",
    "sao",
    "está",
    "esta",
    "estão",
    "estao",
}


@dataclass(frozen=True, slots=True)
class Take:
    index: int
    sentence_ids: tuple[int, ...]
    start_sample: int
    end_sample: int
    text: str
    word_count: int
    complete: bool
    clean: bool
    quality: float

    @property
    def start_sec(self) -> float:
        return round(self.start_sample / 48_000, 3)

    @property
    def end_sec(self) -> float:
        return round(self.end_sample / 48_000, 3)


@dataclass(frozen=True, slots=True)
class TakeGroup:
    keep: tuple[int, ...]
    discard: tuple[int, ...]
    reason: str
    keep_text: tuple[str, ...]
    discard_text: tuple[str, ...]
    start_sec: float
    end_sec: float


def _normalized(text: str) -> str:
    return normalize_text(text)


def _tokens(text: str) -> list[str]:
    return token_list(text)


def _token_set(text: str) -> set[str]:
    return token_set(text)


def _content_tokens(text: str) -> set[str]:
    return content_tokens(text, _STOPWORDS)


def _facts(text: str) -> set[str]:
    numbers = {value.replace(",", ".") for value in _NUMBER.findall(text)}
    urls = {value.casefold() for value in _URL.findall(text)}
    return numbers | urls


def _similarity(left: str, right: str) -> tuple[float, float]:
    a = _normalized(left)
    b = _normalized(right)
    if not a or not b:
        return 0.0, 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    if not left_tokens or not right_tokens:
        return ratio, 0.0
    intersection = len(left_tokens & right_tokens)
    containment = intersection / min(len(left_tokens), len(right_tokens))
    jaccard = intersection / len(left_tokens | right_tokens)
    score = max(ratio, 0.6 * containment + 0.4 * jaccard)
    return score, containment


def _complete(sentence: Sentence) -> bool:
    text = sentence.text.strip()
    if not text:
        return False
    return text.endswith((".", "!", "?")) and len(_tokens(text)) >= 3


def _clean(sentence: Sentence) -> bool:
    words = _tokens(sentence.text)
    if len(words) < 4:
        return False
    grams = [" ".join(words[index : index + 3]) for index in range(len(words) - 2)]
    return len(grams) == len(set(grams))


def _quality(sentences: Sequence[Sentence]) -> float:
    words = [word for sentence in sentences for word in sentence.words]
    if not words:
        return 0.5
    mean = sum(word.probability for word in words) / len(words)
    norms = [_normalized(word.word) for word in words]
    repeats = sum(
        1
        for previous, current in zip(norms, norms[1:], strict=False)
        if previous and previous == current
    )
    return max(0.0, min(1.0, mean - 0.5 * repeats / max(1, len(norms))))


def _make_take(index: int, sentences: Sequence[Sentence]) -> Take:
    text = " ".join(sentence.text.strip() for sentence in sentences if sentence.text.strip())
    words = sum(len(_tokens(sentence.text)) for sentence in sentences)
    return Take(
        index=index,
        sentence_ids=tuple(sentence.id for sentence in sentences),
        start_sample=min(sentence.start_sample for sentence in sentences),
        end_sample=max(sentence.end_sample for sentence in sentences),
        text=text,
        word_count=words,
        complete=_complete(sentences[-1]),
        clean=all(_clean(sentence) for sentence in sentences),
        quality=_quality(sentences),
    )


def segment_takes(
    sentences: Sequence[Sentence],
    *,
    max_pause_ms: int = 1200,
    max_take_seconds: float = 45.0,
    max_sentences: int = 8,
    restart_prefix_words: int = 3,
    restart_max_gap_ms: int = 8000,
    sample_rate: int = 48_000,
) -> list[Take]:
    """Split consecutive sentences into takes at pauses and restarts."""

    ordered = sorted(sentences, key=lambda item: (item.start_sample, item.end_sample, item.id))
    if not ordered:
        return []
    pause_limit = round(max_pause_ms * sample_rate / 1000)
    restart_gap = round(restart_max_gap_ms * sample_rate / 1000)
    takes: list[Take] = []
    current: list[Sentence] = [ordered[0]]
    for sentence in ordered[1:]:
        previous = current[-1]
        gap = sentence.start_sample - previous.end_sample
        duration = sentence.end_sample - current[0].start_sample
        restart = False
        if gap <= restart_gap and len(current) >= 1:
            first_tokens = _tokens(current[0].text)[:restart_prefix_words]
            next_tokens = _tokens(sentence.text)[:restart_prefix_words]
            if (
                len(first_tokens) == restart_prefix_words
                and first_tokens == next_tokens
            ):
                restart = True
            elif first_tokens and next_tokens and first_tokens[0] == next_tokens[0]:
                score, containment = _similarity(current[0].text, sentence.text)
                restart = score >= 0.72 and containment >= 0.6
        if (
            gap >= pause_limit
            or restart
            or duration >= max_take_seconds * sample_rate
            or len(current) >= max_sentences
        ):
            takes.append(_make_take(len(takes), current))
            current = [sentence]
        else:
            current.append(sentence)
    takes.append(_make_take(len(takes), current))
    return takes


def _keeper_score(take: Take, rank: int, total: int) -> float:
    score = 0.0
    score += 2.0 if take.complete else 0.0
    score += 1.5 if take.clean else 0.0
    score += 1.0 * take.quality
    score += 0.02 * min(take.word_count, 50)
    score += 0.05 * (rank / max(1, total - 1))
    return score


def _covers(keeper: Take, candidate: Take, *, min_coverage: float = 0.6) -> bool:
    """A keeper covers a candidate when it keeps the candidate's facts and idea.

    Lexical overlap is a proxy for meaning. Numbers and URLs must always match;
    the remaining content words need to be mostly covered, because a paraphrase
    naturally swaps a few words.
    """

    keeper_tokens = _content_tokens(keeper.text)
    candidate_tokens = _content_tokens(candidate.text)
    if not candidate_tokens:
        return True
    if _facts(candidate.text) - _facts(keeper.text):
        return False
    coverage = len(candidate_tokens & keeper_tokens) / len(candidate_tokens)
    return coverage >= min_coverage


def semantic_duplicate_sentences(
    sentences: Sequence[Sentence],
    discard_ids: set[int],
    *,
    max_gap_seconds: float = 300.0,
    threshold: float = 0.8,
    min_coverage: float = 0.6,
) -> set[int]:
    """Discard earlier sentences that a later sentence restates semantically."""

    from videoflow.application import semantic

    if not semantic.available():
        return set()
    kept = [
        sentence
        for sentence in sentences
        if sentence.id not in discard_ids
        and _complete(sentence)
        and len(sentence.text.split()) >= 4
    ]
    if len(kept) < 2:
        return set()
    vectors = semantic.encode([sentence.text for sentence in kept])
    if vectors is None:
        return set()
    index = {sentence.id: position for position, sentence in enumerate(kept)}
    ordered = sorted(kept, key=lambda item: (item.start_sample, item.id))
    extra: set[int] = set()
    for position, earlier in enumerate(ordered):
        if earlier.id in extra:
            continue
        earlier_tokens = _content_tokens(earlier.text)
        if not earlier_tokens:
            continue
        for later in ordered[position + 1 :]:
            if later.start_sample - earlier.start_sample > max_gap_seconds * 48_000:
                break
            if later.id in extra:
                continue
            if _facts(earlier.text) - _facts(later.text):
                continue
            if semantic.cosine(
                vectors[index[earlier.id]], vectors[index[later.id]]
            ) < threshold:
                continue
            coverage = len(earlier_tokens & _content_tokens(later.text)) / len(
                earlier_tokens
            )
            if coverage >= min_coverage:
                extra.add(earlier.id)
                break
    return extra


def select_duplicate_takes(
    sentences: Sequence[Sentence],
    *,
    min_similarity: float = 0.58,
    min_containment: float = 0.45,
    min_coverage: float = 0.6,
    max_gap_seconds: float = 300.0,
    **segment_options: float | int,
) -> tuple[TakeGroup, ...]:
    """Group duplicate takes and discard attempts fully covered by the keeper."""

    takes = segment_takes(sentences, **segment_options)  # type: ignore[arg-type]
    if len(takes) < 2:
        return ()
    used: set[int] = set()
    groups: list[TakeGroup] = []
    for position, take in enumerate(takes):
        if take.index in used or take.word_count < 4:
            continue
        cluster = [take]
        for candidate in takes[position + 1 :]:
            if candidate.index in used:
                continue
            if candidate.start_sample - take.start_sample > max_gap_seconds * 48_000:
                break
            if candidate.word_count < 4:
                continue
            score, containment = _similarity(take.text, candidate.text)
            if score >= min_similarity and containment >= min_containment:
                cluster.append(candidate)
        if len(cluster) < 2:
            continue
        for item in cluster:
            used.add(item.index)
        ranked = sorted(cluster, key=lambda item: item.start_sample)
        keeper = max(
            ranked,
            key=lambda item: (
                _keeper_score(item, ranked.index(item), len(ranked)),
                item.start_sample,
            ),
        )
        if not keeper.complete or not keeper.clean:
            continue
        restored: list[Take] = []
        discarded: list[Take] = []
        for item in ranked:
            if item.index == keeper.index:
                continue
            if _covers(keeper, item, min_coverage=min_coverage):
                discarded.append(item)
            else:
                restored.append(item)
        if not discarded:
            continue
        discard_ids = tuple(
            identifier for item in discarded for identifier in item.sentence_ids
        )
        keep_ids = tuple(
            identifier
            for item in [keeper, *restored]
            for identifier in item.sentence_ids
        )
        groups.append(
            TakeGroup(
                keep=keep_ids,
                discard=discard_ids,
                reason=(
                    "duplicate take"
                    if not restored
                    else "duplicate take with unique content restored"
                ),
                keep_text=tuple(item.text for item in [keeper, *restored]),
                discard_text=tuple(item.text for item in discarded),
                start_sec=round(min(item.start_sample for item in ranked) / 48_000, 3),
                end_sec=round(max(item.end_sample for item in ranked) / 48_000, 3),
            )
        )
    return tuple(groups)
