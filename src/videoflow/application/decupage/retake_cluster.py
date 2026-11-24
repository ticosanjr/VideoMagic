"""Transitive grouping for distant retakes of the same passage.

A speaker can restart the same sentence five times across several minutes, with
comments or stutters in between. Comparing only adjacent sentences loses those
takes. This module connects valid pairs transitively (Union-Find) and keeps one
complete attempt per connected component.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from videoflow.application.retakes.similarity import (
    _CONTENT_STOPWORDS,
    _NUMBER,
    _PROTECTED,
    _complete,
    _keeper,
    _normalized,
    _similarity,
    _unique_facts,
)
from videoflow.application.text import STOPWORDS, normalize_text, token_list
from videoflow.domain.retakes import Strategy
from videoflow.domain.state import Sentence

_CONTENT_STOPWORDS_ALL = STOPWORDS | _CONTENT_STOPWORDS
_ORDINALS = {
    "primeiro",
    "primeira",
    "segundo",
    "segunda",
    "terceiro",
    "terceira",
    "quarto",
    "quarta",
    "quinto",
    "quinta",
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
}


@dataclass(frozen=True, slots=True)
class MultiTakeCluster:
    keeper_id: int
    discard_ids: tuple[int, ...]
    reason: str
    span_sec: float


def _content_words(text: str) -> list[str]:
    return [
        token
        for token in token_list(normalize_text(text))
        if len(token) >= 3 and token not in _CONTENT_STOPWORDS_ALL
    ]


def _ordinals(text: str) -> set[str]:
    return set(token_list(normalize_text(text))) & _ORDINALS


def _same_fact_guard(earlier: Sentence, later: Sentence) -> bool:
    if _PROTECTED.search(earlier.text) and not _PROTECTED.search(later.text):
        return True
    earlier_numbers = set(_NUMBER.findall(earlier.text))
    later_numbers = set(_NUMBER.findall(later.text))
    if earlier_numbers and earlier_numbers != later_numbers:
        return True
    earlier_ordinals = _ordinals(earlier.text)
    later_ordinals = _ordinals(later.text)
    if earlier_ordinals and later_ordinals and earlier_ordinals != later_ordinals:
        return True
    return _unique_facts(earlier, later)


def is_retake_pair(
    earlier: Sentence,
    later: Sentence,
    *,
    min_similarity: float = 0.58,
    min_prefix_content_words: int = 3,
    min_containment: float = 0.60,
) -> bool:
    """Whether two takes may belong to the same transitive retake cluster."""

    if earlier.id == later.id:
        return False
    if _same_fact_guard(earlier, later):
        return False
    similarity = _similarity(earlier, later)
    earlier_content = _content_words(earlier.text)
    later_content = _content_words(later.text)
    if not earlier_content or not later_content:
        # Short exact repeats still matter even when every word is a stopword.
        return _normalized(earlier.text) == _normalized(later.text)
    earlier_set = set(earlier_content)
    later_set = set(later_content)
    prefix = len(set(earlier_content[:6]) & set(later_content[:6]))
    containment = len(earlier_set & later_set) / len(earlier_set)
    aborted = (
        len(token_list(earlier.text)) <= 0.75 * len(token_list(later.text))
        and containment >= min_containment
    )
    trailing = (
        not _complete(later)
        and len(token_list(later.text)) <= 0.75 * len(token_list(earlier.text))
        and len(later_set & earlier_set) / len(later_set) >= min_containment
    )
    return (
        similarity >= min_similarity
        or prefix >= min_prefix_content_words
        or aborted
        or trailing
    )


def _find(parent: list[int], index: int) -> int:
    while parent[index] != index:
        parent[index] = parent[parent[index]]
        index = parent[index]
    return index


def _union(parent: list[int], left: int, right: int) -> None:
    root_left = _find(parent, left)
    root_right = _find(parent, right)
    if root_left != root_right:
        parent[root_right] = root_left


def cluster_distant_retakes(
    sentences: Sequence[Sentence],
    *,
    sample_rate: int = 48_000,
    max_window_sentences: int = 25,
    max_gap_sec: float = 420.0,
    strategy: Strategy = "keep_last",
    min_similarity: float = 0.58,
    min_prefix_content_words: int = 3,
    min_containment: float = 0.60,
    max_discard_ratio: float = 0.75,
) -> tuple[MultiTakeCluster, ...]:
    """Group 2 to N takes transitively, keeping one complete attempt."""

    ordered = sorted(sentences, key=lambda item: (item.start_sample, item.id))
    if len(ordered) < 2:
        return ()
    rate = max(1, int(sample_rate))
    parent = list(range(len(ordered)))
    for index, earlier in enumerate(ordered):
        last = min(len(ordered), index + 1 + max(1, int(max_window_sentences)))
        for cursor in range(index + 1, last):
            later = ordered[cursor]
            if later.start_sample - earlier.start_sample > max_gap_sec * rate:
                break
            if is_retake_pair(
                earlier,
                later,
                min_similarity=min_similarity,
                min_prefix_content_words=min_prefix_content_words,
                min_containment=min_containment,
            ):
                _union(parent, index, cursor)

    components: dict[int, list[int]] = {}
    for index in range(len(ordered)):
        components.setdefault(_find(parent, index), []).append(index)
    by_index = {index: sentence for index, sentence in enumerate(ordered)}
    clusters: list[MultiTakeCluster] = []
    budget = max(1, int(len(ordered) * max(0.0, min(1.0, max_discard_ratio))))
    discarded_total = 0
    for members in components.values():
        if len(members) < 2 or discarded_total >= budget:
            continue
        texts = {_normalized(by_index[index].text) for index in members}
        if len(texts) == 1:
            keeper = max(
                members,
                key=lambda index: (by_index[index].start_sample, index),
            )
        else:
            keeper = _keeper(members, by_index, strategy)
        discard = [index for index in members if index != keeper]
        # Never discard a unique fact, price, URL, or a numbered list item.
        discard = [
            index
            for index in discard
            if not _same_fact_guard(by_index[index], by_index[keeper])
        ]
        if not discard:
            continue
        remaining = budget - discarded_total
        discard = discard[-remaining:] if len(discard) > remaining else discard
        if not discard:
            continue
        discarded_total += len(discard)
        times = [by_index[index].start_sample for index in members]
        ends = [by_index[index].end_sample for index in members]
        clusters.append(
            MultiTakeCluster(
                keeper_id=by_index[keeper].id,
                discard_ids=tuple(by_index[index].id for index in sorted(discard)),
                reason="transitive distant retake",
                span_sec=round((max(ends) - min(times)) / rate, 3),
            )
        )
    return tuple(clusters)


__all__ = ["MultiTakeCluster", "cluster_distant_retakes", "is_retake_pair"]
