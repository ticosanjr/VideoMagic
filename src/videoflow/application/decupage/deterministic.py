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
from videoflow.application.spans import merge_spans
from videoflow.domain.decupage import Asu, AsuDecision
from videoflow.domain.state import Sentence

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


def build_safe_speech_spans(
    vad_spans: Sequence[tuple[int, int]],
    kept_sentences: Sequence[Sentence],
    discard_ids: set[int],
    *,
    sample_rate: int = 48_000,
    min_word_prob: float = 0.45,
    pad_before_ms: int = 90,
    pad_after_ms: int = 150,
    long_cut_review_sec: float = 15.0,
    duration_samples: int | None = None,
    rms_profile: dict[str, Any] | None = None,
) -> tuple[list[tuple[int, int]], list[dict[str, Any]]]:
    """Union VAD with transcribed words and flag long removed gaps.

    A word is protected when its ASR probability is at least
    ``min_word_prob``. The union is padded so a low-energy but transcribed
    phrase cannot be mistaken for silence. Gaps larger than
    ``long_cut_review_sec`` always appear in the report; gaps with remaining
    words or audible RMS are marked for human review.
    """

    rate = max(1, int(sample_rate))
    pad_before = max(0, round(rate * max(0, pad_before_ms) / 1000))
    pad_after = max(0, round(rate * max(0, pad_after_ms) / 1000))
    words = [
        word
        for sentence in kept_sentences
        if sentence.id not in discard_ids
        for word in sentence.words
    ]
    asr_spans: list[tuple[int, int]] = []
    for word in words:
        if word.probability < min_word_prob:
            continue
        if word.end_sample <= word.start_sample:
            continue
        asr_spans.append(
            (max(0, word.start_sample - pad_before), word.end_sample + pad_after)
        )
    spans = merge_spans([*vad_spans, *asr_spans])
    if duration_samples is not None:
        limit = max(0, int(duration_samples))
        spans = [
            (min(limit, start), min(limit, end))
            for start, end in spans
            if end > start and start < limit
        ]
        spans = merge_spans(spans)
        total = limit
    else:
        total = max((end for _start, end in spans), default=0)

    flagged: list[dict[str, Any]] = []
    threshold = max(0.0, float(long_cut_review_sec)) * rate
    cursor = 0
    for start, end in [*spans, (total, total)]:
        gap_start, gap_end = cursor, start
        if gap_end - gap_start > threshold:
            removed_words = [
                word
                for word in words
                if word.end_sample > gap_start and word.start_sample < gap_end
            ]
            rms = _mean_rms_db(rms_profile, gap_start, gap_end)
            requires_review = bool(removed_words) or (
                rms is not None and rms > -42.0
            )
            flagged.append(
                {
                    "start_sec": round(gap_start / rate, 3),
                    "end_sec": round(gap_end / rate, 3),
                    "duration_sec": round((gap_end - gap_start) / rate, 3),
                    "rms_dbfs": rms,
                    "word_count": len(removed_words),
                    "requires_review": requires_review,
                    "reason": (
                        "long_gap_with_speech"
                        if removed_words
                        else "long_gap"
                    ),
                }
            )
        cursor = max(cursor, end)
    return spans, flagged


def _mean_rms_db(
    profile: dict[str, Any] | None,
    start_sample: int,
    end_sample: int,
) -> float | None:
    if not profile:
        return None
    values = profile.get("db") or []
    if not values:
        return None
    hop = max(1, int(profile.get("hop_samples") or 1))
    low = max(0, start_sample // hop)
    high = min(len(values), max(low + 1, end_sample // hop))
    window = values[low:high]
    if not window:
        return None
    try:
        return round(sum(float(item) for item in window) / len(window), 3)
    except (TypeError, ValueError):
        return None
