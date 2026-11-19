"""Deterministic pre-LLM decupage decisions.

This pass is deliberately cheap and conservative: it tags isolated noise,
groups near-duplicate ASUs, and exposes stutter candidates. The LLM sees the
result but never receives timestamps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from videoflow.domain.decupage import Asu, AsuDecision

_WORD = re.compile(r"[0-9a-zà-ÿ]+")
_REMOVE_NOISE = {
    "cough",
    "throat clearing",
    "sneeze",
    "snort",
    "gasp",
    "knock",
    "tap",
    "thump",
}
_HALLUCINATION = re.compile(
    r"legendas?\s+(pela|da)\s+comunidade|obrigado por assistir|"
    r"inscreva-se no canal|at[eé] a próxima",
    re.IGNORECASE,
)
_PROTECTED = re.compile(
    r"https?://|www\.|r\$|\$|€|£|\bpre[çc]o\b|\bpatrocin|\bapoia\s+esse\s+v[íi]deo|"
    r"\blink\b|\bcupom\b|\bdesconto\b|\bpromo[çc]|\boferta\b|\bassinatura\b|"
    r"\bplano\b|\bgr[áa]tis\b|\bloja\b|\bcomprar\b|\bclique\b|\binscreve\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class PrefilterResult:
    asus: list[Asu]
    decisions: list[AsuDecision]
    report: dict[str, Any]


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.casefold())


def _token_set_ratio(left: str, right: str) -> float:
    a = set(_tokens(left))
    b = set(_tokens(right))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _prefix_ratio(left: str, right: str, *, words: int = 6) -> float:
    a = " ".join(_tokens(left)[:words])
    b = " ".join(_tokens(right)[:words])
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _protected(text: str) -> bool:
    return bool(_PROTECTED.search(text))


def _noise_decision(asu: Asu) -> AsuDecision | None:
    words = len(asu.words)
    if words <= 2:
        for event in asu.noise_events:
            try:
                score = float(event.get("score") or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            label = str(event.get("label") or "").casefold()
            if label in _REMOVE_NOISE and score >= 0.55:
                return AsuDecision(
                    asu_id=asu.asu_id,
                    action="REMOVE",
                    category="NOISE",
                    confidence=round(min(1.0, score), 4),
                    reason=f"{label} isolated over a short ASU",
                )
    if words <= 3 and _HALLUCINATION.search(asu.text) and asu.avg_word_prob <= 0.4:
        return AsuDecision(
            asu_id=asu.asu_id,
            action="REMOVE",
            category="NOISE",
            confidence=0.8,
            reason="low-confidence transcript hallucination",
        )
    return None


def prefilter(
    asus: list[Asu],
    *,
    lookahead_seconds: float = 45.0,
    min_words: int = 3,
    prefix_similarity: float = 0.78,
    token_similarity: float = 0.72,
    max_group_seconds: float = 180.0,
) -> PrefilterResult:
    """Return grouped ASUs and deterministic quarantine decisions."""

    ordered = sorted(asus, key=lambda item: (item.start_sample, item.asu_id))
    decisions: list[AsuDecision] = []
    for asu in ordered:
        noise = _noise_decision(asu)
        if noise is not None:
            decisions.append(noise)

    grouped: dict[str, Asu] = {}
    group_index = 0
    used: set[str] = set()
    for index, asu in enumerate(ordered):
        if asu.asu_id in used:
            continue
        if _protected(asu.text):
            grouped[asu.asu_id] = asu
            continue
        candidates: list[Asu] = [asu]
        for later in ordered[index + 1 : index + 7]:
            if later.asu_id in used or _protected(later.text):
                break
            if later.start_sec - asu.start_sec > lookahead_seconds:
                break
            if later.end_sec - asu.start_sec > max_group_seconds:
                break
            if len(_tokens(asu.text)) < min_words or len(_tokens(later.text)) < min_words:
                continue
            prefix = _prefix_ratio(asu.text, later.text)
            overlap = _token_set_ratio(asu.text, later.text)
            if prefix >= prefix_similarity or overlap >= token_similarity:
                candidates.append(later)
        if len(candidates) < 2:
            grouped[asu.asu_id] = asu
            continue
        group_index += 1
        group_id = f"RG_{group_index:04d}"
        for item in candidates:
            used.add(item.asu_id)
            grouped[item.asu_id] = item.model_copy(
                update={"retake_group_id": group_id}
            )
        decisions.append(
            AsuDecision(
                asu_id=candidates[0].asu_id,
                action="REVIEW",
                category="RETAKE_GROUP",
                confidence=0.5,
                reason=f"fuzzy retake group {group_id}",
            )
        )

    # Preserve original order even when an ASU was skipped by the group pass.
    ordered_groups = [grouped.get(item.asu_id, item) for item in ordered]
    report = {
        "schema_version": 1,
        "asus": len(ordered_groups),
        "groups": group_index,
        "decisions": len(decisions),
        "lookahead_seconds": lookahead_seconds,
        "noise": sum(1 for item in decisions if item.category == "NOISE"),
        "stutter_candidates": sum(
            1 for item in ordered_groups if item.has_stutter_candidate
        ),
    }
    return PrefilterResult(ordered_groups, decisions, report)
