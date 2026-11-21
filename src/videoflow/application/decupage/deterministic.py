"""Deterministic decupage candidates that do not depend on an LLM.

The semantic pass is optional. Repetitions, false starts, and short-word
stutters are objective enough to remove deterministically, so the decupage
still works when ``llm_policy=none`` or when the caller never submits
decisions. Ambiguous cases (strong punctuation, low confidence, numbers) are
returned as review flags for the LLM pass instead of being cut.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from videoflow.application.repetition import (
    RepeatWord,
    detect_words,
    normalise_token,
)
from videoflow.domain.decupage import Asu, AsuDecision

_REMOVE_ACTIONS = {
    "REMOVE",
    "REMOVE_RETAKE",
    "REMOVE_NOISE",
    "REMOVE_FILLER",
    "QUARANTINE",
}


@dataclass
class DeterministicResult:
    decisions: list[AsuDecision] = field(default_factory=list)
    cuts: list[dict[str, Any]] = field(default_factory=list)
    flags: list[dict[str, str]] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


def _origin(asu: Asu) -> list[tuple[str, int, Any]]:
    return [(asu.asu_id, word.idx, word) for word in asu.words]


def deterministic_repeats(
    asus: list[Asu],
    existing: Sequence[AsuDecision] = (),
    *,
    sample_rate: int = 48_000,
    max_gap_sec: float = 1.2,
) -> DeterministicResult:
    """Return TRIM_WORDS decisions, explicit cuts, and review flags."""

    removed = {item.asu_id for item in existing if item.action in _REMOVE_ACTIONS}
    decided = {
        item.asu_id
        for item in existing
        if item.action in {"TRIM_WORDS"} | _REMOVE_ACTIONS
    }
    origin: list[tuple[str, int, Any]] = []
    tokens: list[RepeatWord] = []
    for asu in asus:
        if asu.asu_id in removed:
            continue
        for asu_id, word_index, word in _origin(asu):
            norm = normalise_token(word.w)
            if not norm:
                continue
            origin.append((asu_id, word_index, word))
            tokens.append(
                RepeatWord(
                    index=len(origin) - 1,
                    sentence_id=0,
                    text=word.w,
                    norm=norm,
                    start_sample=word.start_sample,
                    end_sample=word.end_sample,
                    probability=float(word.p),
                )
            )
    if len(tokens) < 2:
        return DeterministicResult(stats={"repeats": 0, "ambiguous": 0, "cuts": 0})

    order = sorted(range(len(tokens)), key=lambda index: tokens[index].start_sample)
    origin = [origin[index] for index in order]
    tokens = [
        RepeatWord(
            index=position,
            sentence_id=tokens[index].sentence_id,
            text=tokens[index].text,
            norm=tokens[index].norm,
            start_sample=tokens[index].start_sample,
            end_sample=tokens[index].end_sample,
            probability=tokens[index].probability,
        )
        for position, index in enumerate(order)
    ]

    plan = detect_words(tokens, sample_rate=sample_rate, max_gap_sec=max_gap_sec)
    result = DeterministicResult()
    for cut in plan.cuts:
        groups: dict[str, list[int]] = {}
        for index in range(cut.first_index, cut.last_index + 1):
            asu_id, word_index, _word = origin[index]
            groups.setdefault(asu_id, []).append(word_index)
        if len(groups) == 1:
            asu_id, indices = next(iter(groups.items()))
            if asu_id not in decided:
                result.decisions.append(
                    AsuDecision(
                        asu_id=asu_id,
                        action="TRIM_WORDS",
                        category="STUTTER",
                        confidence=cut.confidence,
                        remove_word_indices=sorted(set(indices)),
                        reason=f"deterministic repeat: {cut.text}",
                    )
                )
                decided.add(asu_id)
                continue
        for index in range(cut.first_index, cut.last_index + 1):
            asu_id, _word_index, word = origin[index]
            result.cuts.append(
                {
                    "asu_id": asu_id,
                    "start_sample": word.start_sample,
                    "end_sample": word.end_sample,
                    "reason": "stutter",
                }
            )
    for cut in plan.ambiguous:
        asu_id, _word_index, _word = origin[cut.first_index]
        result.flags.append(
            {
                "asu_id": asu_id,
                "category": "REVIEW",
                "reason": f"ambiguous repetition: {cut.text}",
            }
        )
    result.stats = {
        "repeats": len(plan.cuts),
        "ambiguous": len(plan.ambiguous),
        "cuts": len(result.cuts),
    }
    return result


__all__ = ["DeterministicResult", "deterministic_repeats"]
