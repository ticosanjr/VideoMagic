"""Retake unique-content guards and manual overrides."""

from __future__ import annotations

from collections.abc import Sequence
from difflib import SequenceMatcher

from videoflow.application.retakes.models import RetakeGroup
from videoflow.application.retakes.similarity import _normalized, _tokens
from videoflow.domain.errors import InvalidRetakeIdsError
from videoflow.domain.state import ManualOverride, Sentence


def _text_similarity(left: str, right: str) -> float:
    a = _normalized(left)
    b = _normalized(right)
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return ratio
    overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    return max(ratio, overlap)


def _guard_unique_discards(
    groups: Sequence[RetakeGroup],
    *,
    min_similarity: float = 0.33,
    short_words: int = 4,
) -> tuple[list[RetakeGroup], int]:
    """Restore long discarded sentences that look like new content.

    The model is good at paraphrases but can over-group list items or adjacent
    ideas. A long sentence with almost no lexical overlap with the keeper is
    safer to keep; short stumbles such as "Duvida!" are still discarded.
    """

    guarded: list[RetakeGroup] = []
    restored = 0
    for group in groups:
        kept_discard: list[int] = []
        kept_text: list[str] = []
        for identifier, text in zip(group.discard, group.discard_text, strict=False):
            similarity = max(
                (_text_similarity(text, candidate) for candidate in group.keep_text),
                default=0.0,
            )
            if similarity < min_similarity and len(_tokens(text)) > short_words:
                restored += 1
                continue
            kept_discard.append(identifier)
            kept_text.append(text)
        if not kept_discard:
            continue
        guarded.append(
            RetakeGroup(
                keep=group.keep,
                discard=tuple(kept_discard),
                reason=group.reason,
                keep_text=group.keep_text,
                discard_text=tuple(kept_text),
                start_sec=group.start_sec,
                end_sec=group.end_sec,
            )
        )
    return guarded, restored


def _reconcile_groups(
    groups: Sequence[RetakeGroup],
    discard: set[int],
) -> list[RetakeGroup]:
    reconciled: list[RetakeGroup] = []
    for group in groups:
        remaining = tuple(identifier for identifier in group.discard if identifier in discard)
        if not remaining:
            continue
        reconciled.append(
            RetakeGroup(
                keep=group.keep,
                discard=remaining,
                reason=group.reason,
                keep_text=group.keep_text,
                discard_text=group.discard_text,
                start_sec=group.start_sec,
                end_sec=group.end_sec,
            )
        )
    return reconciled


def apply_manual_overrides(
    discard: Sequence[int],
    manual: Sequence[ManualOverride],
    valid_ids: set[int],
) -> tuple[list[int], list[int]]:
    """Layer manual discard/restore actions over the automatic discard list.

    Returns the sorted discard ids and the manual discard ids that survived
    (i.e. were not restored by a later override). Raises when an override
    references a sentence that is not in the transcript.
    """

    unknown = [item.sentence_id for item in manual if item.sentence_id not in valid_ids]
    if unknown:
        raise InvalidRetakeIdsError(unknown)
    discarded = set(discard)
    for item in manual:
        if item.action == "discard":
            discarded.add(item.sentence_id)
        else:
            discarded.discard(item.sentence_id)
    result = sorted(discarded)
    manual_discard_ids = sorted(
        {item.sentence_id for item in manual if item.action == "discard"} & discarded
    )
    return result, manual_discard_ids


def _group_for(
    order: dict[int, Sentence],
    keep: tuple[int, ...],
    discard: tuple[int, ...],
    reason: str,
) -> RetakeGroup:
    """Build a report group with text and sample-aligned bounds."""

    members = [order[identifier] for identifier in (*keep, *discard)]
    return RetakeGroup(
        keep=keep,
        discard=discard,
        reason=reason,
        keep_text=tuple(order[identifier].text for identifier in keep),
        discard_text=tuple(order[identifier].text for identifier in discard),
        start_sec=round(min(item.start_sample for item in members) / 48000, 3),
        end_sec=round(max(item.end_sample for item in members) / 48000, 3),
    )

