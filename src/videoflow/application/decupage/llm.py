"""Sliding-window LLM contract for decupage decisions.

The model receives ASU ids and word indexes only. This module validates every
decision and converts it into source-sample cuts; the timeline is not mutated.
"""

from __future__ import annotations

from typing import Any

from videoflow.domain.decupage import Asu, AsuDecision, DecupageWindow

PASS1_INSTRUCTIONS = """\
You are the editorial decupage pass for a talking-head video.
Use only asu_id and word indexes. Never generate timestamps.
Rules:
1. Last-take-wins: remove earlier incomplete/hesitant takes and keep the last
   complete, fluent take. If the last take is broken and the previous one is
   clean, keep the clean one and explain.
2. Do not remove intentional rhetorical repetition or new information.
3. Remove editing meta-talk, abandoned sentences, and isolated fillers.
4. TRIM_WORDS only for an ASU with has_stutter_candidate=true.
5. When unsure, return KEEP with confidence <= 0.70 and category REVIEW.
Return JSON:
{"decisions":[{"asu_id":"ASU_0001",
"action":"KEEP|REMOVE|TRIM_WORDS|REVIEW",
"category":"RETAKE|ERROR|FILLER|STUTTER|REVIEW",
"confidence":0.0,"remove_word_indices":[],"reason":"short"}]}
Only use ids from the window.
"""

AUDIT_INSTRUCTIONS = """\
You are a continuity auditor for a decupage plan.
You receive only the text of ASUs marked KEEP, without timestamps.
Find sentences that became orphaned or duplicated at a window boundary.
Return JSON: {"restore_asu_ids":[ints],"reason":"short"}.
Do not restore intentional rhetoric. Only use ids present in the payload.
"""


def compact_asu(asu: Asu) -> dict[str, Any]:
    return {
        "asu_id": asu.asu_id,
        "text": asu.text,
        "pause_before": asu.pause_before,
        "pause_after": asu.pause_after,
        "avg_word_prob": asu.avg_word_prob,
        "retake_group_id": asu.retake_group_id,
        "has_stutter_candidate": asu.has_stutter_candidate,
        "words": [{"idx": word.idx, "w": word.w, "p": word.p} for word in asu.words],
    }


def build_windows(
    asus: list[Asu],
    *,
    window_sec: float = 240.0,
    overlap_sec: float = 45.0,
    max_words: int = 600,
) -> list[DecupageWindow]:
    """Build overlapping 3-4 min windows without splitting an ASU."""

    ordered = sorted(asus, key=lambda item: (item.start_sample, item.asu_id))
    windows: list[DecupageWindow] = []
    index = 0
    while index < len(ordered):
        start = ordered[index].start_sec
        cursor = index
        words = 0
        selected: list[Asu] = []
        while cursor < len(ordered):
            item = ordered[cursor]
            count = len(item.words)
            if selected and (
                item.end_sec - start > window_sec or words + count > max_words
            ):
                break
            selected.append(item)
            words += count
            cursor += 1
        if not selected:
            selected = [ordered[index]]
            cursor = index + 1
        windows.append(
            DecupageWindow(
                window_id=f"WIN_{len(windows) + 1:03d}",
                asu_ids=[item.asu_id for item in selected],
                asus=[compact_asu(item) for item in selected],
                word_count=sum(len(item.words) for item in selected),
            )
        )
        if cursor >= len(ordered):
            break
        end_sec = selected[-1].end_sec
        next_index = cursor
        while next_index > index + 1 and ordered[next_index - 1].start_sec >= end_sec - overlap_sec:
            next_index -= 1
        # Keep at least six ASUs of context when the window is large.
        next_index = min(next_index, max(index + 1, cursor - 6))
        index = max(index + 1, next_index)
    return windows


def pass1_prompt(window: DecupageWindow) -> str:
    import json

    return (
        PASS1_INSTRUCTIONS
        + "\nWindow: "
        + window.window_id
        + "\nASUs:\n"
        + json.dumps(window.asus, ensure_ascii=False)
    )


def audit_prompt(asus: list[Asu], decisions: list[AsuDecision]) -> str:
    import json

    removed = {
        item.asu_id for item in decisions if item.action == "REMOVE"
    }
    keep = [
        {"asu_id": item.asu_id, "text": item.text}
        for item in asus
        if item.asu_id not in removed
    ]
    candidates = [
        {"asu_id": item.asu_id, "text": item.text}
        for item in asus
        if item.asu_id in removed
    ]
    return (
        AUDIT_INSTRUCTIONS
        + "\nKEEP ASUs:\n"
        + json.dumps(keep, ensure_ascii=False)
        + "\nREMOVED CANDIDATES (restore only if needed):\n"
        + json.dumps(candidates, ensure_ascii=False)
    )


def parse_decisions(
    raw: dict[str, Any],
    *,
    allowed: set[str],
    asus: dict[str, Asu],
) -> list[AsuDecision]:
    values = raw.get("decisions")
    if not isinstance(values, list):
        return []
    result: list[AsuDecision] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("asu_id") or "")
        if identifier not in allowed or identifier not in asus:
            continue
        action = str(item.get("action") or "KEEP").upper()
        if action not in {"KEEP", "REMOVE", "TRIM_WORDS", "REVIEW", "RESTORE"}:
            continue
        asu = asus[identifier]
        indices: list[int] = []
        if action == "TRIM_WORDS":
            if not asu.has_stutter_candidate:
                continue
            raw_indices = item.get("remove_word_indices")
            if not isinstance(raw_indices, list):
                continue
            for value in raw_indices:
                try:
                    number = int(value)
                except (TypeError, ValueError):
                    continue
                if 0 <= number < len(asu.words):
                    indices.append(number)
            if not indices:
                continue
        try:
            confidence = float(item.get("confidence", 1.0))
        except (TypeError, ValueError):
            confidence = 1.0
        result.append(
            AsuDecision(
                asu_id=identifier,
                action=action,  # type: ignore[arg-type]
                category=str(item.get("category") or ""),
                confidence=max(0.0, min(1.0, confidence)),
                remove_word_indices=sorted(set(indices)),
                reason=str(item.get("reason") or "")[:500],
            )
        )
    return result


def apply_decisions(
    asus: list[Asu],
    decisions: list[AsuDecision],
    *,
    max_discard_ratio: float = 0.45,
) -> tuple[list[Asu], list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    """Apply validated decisions to an ASU copy and return source cuts."""

    remove_ids = {
        item.asu_id for item in decisions if item.action == "REMOVE"
    }
    restore_ids = {
        item.asu_id for item in decisions if item.action == "RESTORE"
    }
    remove_ids -= restore_ids
    limit = max(1, int(len(asus) * max_discard_ratio))
    if len(remove_ids) > limit:
        keep = [
            item.asu_id
            for item in asus
            if item.asu_id not in remove_ids
        ]
        keep.extend(sorted(remove_ids)[:limit])
        remove_ids = {item.asu_id for item in asus if item.asu_id not in set(keep)}

    updated: list[Asu] = []
    cuts: list[dict[str, Any]] = []
    flags: list[dict[str, str]] = []
    for asu in asus:
        if asu.asu_id in remove_ids:
            cuts.append(
                {
                    "asu_id": asu.asu_id,
                    "start_sample": asu.start_sample,
                    "end_sample": asu.end_sample,
                    "reason": "decupage_remove",
                }
            )
            continue
        trimmed = next(
            (
                item
                for item in decisions
                if item.asu_id == asu.asu_id and item.action == "TRIM_WORDS"
            ),
            None,
        )
        if trimmed is not None:
            removed = set(trimmed.remove_word_indices)
            kept_words = [
                word for index, word in enumerate(asu.words) if index not in removed
            ]
            for index in removed:
                if index < len(asu.words):
                    word = asu.words[index]
                    cuts.append(
                        {
                            "asu_id": asu.asu_id,
                            "start_sample": word.start_sample,
                            "end_sample": word.end_sample,
                            "reason": "decupage_trim",
                        }
                    )
            if not kept_words:
                cuts.append(
                    {
                        "asu_id": asu.asu_id,
                        "start_sample": asu.start_sample,
                        "end_sample": asu.end_sample,
                        "reason": "decupage_remove",
                    }
                )
                continue
            asu = asu.model_copy(
                update={
                    "start_sample": kept_words[0].start_sample,
                    "end_sample": kept_words[-1].end_sample,
                    "start_sec": kept_words[0].start_sec,
                    "end_sec": kept_words[-1].end_sec,
                    "text": " ".join(word.w for word in kept_words),
                    "words": [
                        word.model_copy(update={"idx": position})
                        for position, word in enumerate(kept_words)
                    ],
                }
            )
        updated.append(asu)
        review = next(
            (
                item
                for item in decisions
                if item.asu_id == asu.asu_id and item.action in {"REVIEW", "RESTORE"}
            ),
            None,
        )
        if review is not None:
            flags.append(
                {
                    "asu_id": asu.asu_id,
                    "category": review.category or "REVIEW",
                    "reason": review.reason,
                }
            )
    summary = {
        "asus_before": len(asus),
        "asus_after": len(updated),
        "removed": len(remove_ids),
        "trimmed": sum(1 for item in decisions if item.action == "TRIM_WORDS"),
        "review_flags": len(flags),
        "cuts": len(cuts),
    }
    return updated, cuts, flags, summary


def parse_audit(raw: dict[str, Any], allowed: set[str]) -> list[AsuDecision]:
    values = raw.get("restore_asu_ids")
    if not isinstance(values, list):
        return []
    result: list[AsuDecision] = []
    for value in values:
        identifier = str(value)
        if identifier not in allowed:
            continue
        result.append(
            AsuDecision(
                asu_id=identifier,
                action="RESTORE",
                category="CONTINUITY",
                confidence=0.7,
                reason=str(raw.get("reason") or "continuity audit")[:500],
            )
        )
    return result
