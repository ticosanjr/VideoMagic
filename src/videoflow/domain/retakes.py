"""Retake guard.

The LLM may propose discards. It may not drop the keeper of a repetition
cluster. ``keep_last`` always keeps the last sentence in the cluster.
``keep_best`` keeps the highest supplied score, and falls back to the last
sentence when scores are missing. Unknown ids are a hard error.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from videoflow.domain.errors import InvalidRetakeIdsError

Strategy = Literal["keep_last", "keep_best"]


@dataclass(frozen=True, slots=True)
class RepetitionCluster:
    sentence_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.sentence_ids:
            raise ValueError("cluster must contain at least one sentence")
        if len(set(self.sentence_ids)) != len(self.sentence_ids):
            raise ValueError("duplicate ids in cluster")


@dataclass(frozen=True, slots=True)
class GuardResult:
    discard_sentence_ids: tuple[int, ...]
    restored_sentence_ids: tuple[int, ...]
    reasoning: str


def normalize_sentence_text(text: str) -> str:
    collapsed = " ".join(text.casefold().split())
    return collapsed.strip(" .,!?;:\"'")


def cluster_exact_repetitions(
    sentences: Sequence[tuple[int, str]],
) -> tuple[RepetitionCluster, ...]:
    """Group consecutive sentences whose normalized text is identical.

    A single sentence is not a retake. Empty text does not cluster.
    """

    clusters: list[RepetitionCluster] = []
    index = 0
    items = list(sentences)
    while index < len(items):
        sentence_id, text = items[index]
        key = normalize_sentence_text(text)
        if not key:
            index += 1
            continue
        group = [sentence_id]
        cursor = index + 1
        while cursor < len(items) and normalize_sentence_text(items[cursor][1]) == key:
            group.append(items[cursor][0])
            cursor += 1
        if len(group) >= 2:
            clusters.append(RepetitionCluster(tuple(group)))
        index = cursor if cursor > index + 1 else index + 1
    return tuple(clusters)


def apply_retake_guard(
    discard_sentence_ids: Sequence[int],
    *,
    clusters: Sequence[RepetitionCluster],
    valid_ids: Sequence[int],
    strategy: Strategy = "keep_last",
    scores: Mapping[int, float] | None = None,
) -> GuardResult:
    """Drop illegal discards and restore the keeper of each cluster."""

    valid = set(valid_ids)
    unknown = [item for item in discard_sentence_ids if item not in valid]
    if unknown:
        raise InvalidRetakeIdsError(unknown)

    discard = set(discard_sentence_ids)
    restored: list[int] = []
    notes: list[str] = []
    for cluster in clusters:
        keeper = _keeper(cluster, strategy, scores)
        if keeper in discard:
            discard.remove(keeper)
            restored.append(keeper)
            notes.append(f"restored sentence {keeper} as the {strategy} keeper")

    reasoning = "; ".join(notes) if notes else "no keeper was discarded"
    return GuardResult(
        discard_sentence_ids=tuple(sorted(discard)),
        restored_sentence_ids=tuple(sorted(set(restored))),
        reasoning=reasoning,
    )


def _keeper(
    cluster: RepetitionCluster,
    strategy: Strategy,
    scores: Mapping[int, float] | None,
) -> int:
    if strategy == "keep_best" and scores:
        scored = [item for item in cluster.sentence_ids if item in scores]
        if scored:
            return max(scored, key=lambda item: (scores[item], item))
    return cluster.sentence_ids[-1]
