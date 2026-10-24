"""Channel scoring profiles, re-ranking, and golden-set metrics."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

PROFILES: dict[str, dict[str, float]] = {
    "default": {},
    "hook": {"markers": 2.5, "question": 1.5, "exclamation": 1.3, "duration": 0.9},
    "education": {
        "numbers": 2.5,
        "question": 1.4,
        "prompt": 1.5,
        "duration": 1.1,
        "markers": 0.7,
    },
    "podcast": {
        "duration": 1.0,
        "markers": 0.3,
        "question": 0.5,
        "payoff": 3.0,
        "completeness": 2.0,
        "duration_fit": 1.0,
    },
    "tiktok": {
        "markers": 1.2,
        "exclamation": 3.0,
        "question": 1.2,
        "duration": 0.8,
        "hook_strength": 5.0,
    },
    "youtube": {"numbers": 1.4, "prompt": 1.4, "duration": 1.2, "markers": 1.1},
}
DIVERSITY_THRESHOLD = 0.75


def profile_weights(profile: str, analytics: dict[str, float] | None = None) -> dict[str, float]:
    """Return the multiplier table for a profile, merged with analytics weights."""

    weights = dict(PROFILES.get(profile, PROFILES["default"]))
    if analytics:
        for key, value in analytics.items():
            weights[str(key)] = float(value)
    return weights


def _terms(text: str) -> set[str]:
    return {
        item
        for item in "".join(char.lower() if char.isalnum() else " " for char in text).split()
        if len(item) > 3
    }


def similar(left: str, right: str) -> float:
    """Jaccard similarity over content words, used for duplicate detection."""

    a = _terms(left)
    b = _terms(right)
    shared = a & b
    if len(shared) < 2:
        return 0.0
    return len(shared) / len(a | b)


def rerank(
    clips: Sequence[Any],
    weights: dict[str, float],
    *,
    diversity_threshold: float = DIVERSITY_THRESHOLD,
    top_k: int = 0,
) -> list[Any]:
    """Apply profile weights, sort by score, and drop near-duplicate titles."""

    scored = []
    for clip in clips:
        total = 0.0
        breakdown = []
        for name, value in getattr(clip, "score_breakdown", ()):
            contribution = float(value) * float(weights.get(name, 1.0))
            total += contribution
            breakdown.append((name, round(contribution, 3)))
        scored.append(
            replace(
                clip,
                score=round(total, 3),
                virality_score=min(100.0, round(total * 4.0, 1)),
                score_breakdown=tuple(breakdown),
            )
        )
    scored.sort(key=lambda item: item.score, reverse=True)
    selected: list[Any] = []
    for clip in scored:
        if any(
            similar(clip.title, item.title) >= diversity_threshold for item in selected
        ):
            continue
        selected.append(clip)
        if top_k and len(selected) >= top_k:
            break
    return selected


def _group_key(sentence_ids: Sequence[int]) -> set[int]:
    return {int(item) for item in sentence_ids}


def _overlap(left: set[int], right: set[int]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def evaluate_cases(
    cases: Sequence[dict[str, Any]],
    *,
    top_k: int = 2,
    use_case_profiles: bool = True,
    default_profile: str = "default",
) -> dict[str, Any]:
    """Score heuristic selection against ideal clips from the golden set."""

    from videoflow.application.shorts import select_shorts
    from videoflow.domain.state import Sentence

    started = time.perf_counter()
    hits = 0
    selected_total = 0
    ideal_total = 0
    ideal_hit = 0
    duplicate_pairs = 0
    sentence_union: set[int] = set()
    ideal_union: set[int] = set()
    approved_total = 0
    approved_hit = 0
    per_case: list[dict[str, Any]] = []

    for case in cases:
        sample_rate = 1000
        sentences = [
            Sentence(
                id=int(item["id"]),
                start_sample=int(round(float(item["start_sec"]) * sample_rate)),
                end_sample=int(round(float(item["end_sec"]) * sample_rate)),
                text=str(item["text"]),
            )
            for item in case["sentences"]
        ]
        minimum = int(round(float(case.get("min_sec", 20)) * sample_rate))
        maximum = int(round(float(case.get("max_sec", 60)) * sample_rate))
        profile = (
            str(case.get("profile", default_profile))
            if use_case_profiles
            else default_profile
        )
        clips = select_shorts(
            sentences,
            min_samples=minimum,
            max_samples=maximum,
            count=int(case.get("count", top_k + 2)),
            min_clips=1,
            selection_mode="heuristic",
            sample_rate=sample_rate,
            weights=profile_weights(profile) if use_case_profiles else None,
        )
        ranked = rerank(clips, profile_weights(profile), top_k=top_k)
        ideal_groups = [_group_key(group) for group in case.get("ideal", [])]
        case_hits = 0
        for clip in ranked:
            chosen = _group_key(clip.sentence_ids)
            sentence_union |= chosen
            if any(group <= chosen for group in ideal_groups):
                case_hits += 1
        covered = {
            index
            for index, group in enumerate(ideal_groups)
            if any(group <= _group_key(clip.sentence_ids) for clip in ranked)
        }
        for left in range(len(ranked)):
            for right in range(left + 1, len(ranked)):
                if (
                    similar(ranked[left].title, ranked[right].title)
                    >= DIVERSITY_THRESHOLD
                ):
                    duplicate_pairs += 1
        approved = case.get("approved") or []
        for index, group in enumerate(ideal_groups):
            if not (isinstance(approved, list) and index < len(approved) and approved[index]):
                continue
            approved_total += 1
            if any(group <= _group_key(clip.sentence_ids) for clip in ranked):
                approved_hit += 1
        for group in ideal_groups:
            ideal_union |= group
        hits += case_hits
        selected_total += len(ranked)
        ideal_total += len(ideal_groups)
        ideal_hit += len(covered)
        per_case.append(
            {
                "id": case.get("id", ""),
                "profile": profile,
                "selected": [clip.title for clip in ranked],
                "hits": case_hits,
                "precision": round(case_hits / max(1, len(ranked)), 4),
                "covered_ideals": len(covered),
            }
        )

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "cases": len(cases),
        "top_k": top_k,
        "precision_at_k": round(hits / max(1, selected_total), 4),
        "recall": round(ideal_hit / max(1, ideal_total), 4),
        "duplicates": duplicate_pairs,
        "coverage": round(len(sentence_union & ideal_union) / max(1, len(ideal_union)), 4),
        "approval_rate": (
            round(approved_hit / approved_total, 4) if approved_total else None
        ),
        "latency_ms": elapsed_ms,
        "cost_usd": 0.0,
        "per_case": per_case,
    }
