"""Retake grouping, merging, validation, and chunking."""

from __future__ import annotations

from collections.abc import Sequence

from videoflow.application.retakes.models import RetakeGroup
from videoflow.application.retakes.similarity import (
    _ELLIPSIS,
    _STRICTNESS_RULES,
    _choose_keeper,
    _has_content,
    _keeper,
    _normalized,
    _similarity,
    _unique_facts,
)
from videoflow.domain.retakes import Strategy
from videoflow.domain.state import Sentence

PROMPT_HEADER = """\
You are cleaning a talking-head transcript for a video editor.
Your job is to find retakes, not topics.

A retake group is two or more attempts at the same passage or idea. It includes:
- exact repeats;
- paraphrases where the speaker changes some words but keeps the same meaning;
- aborted starts, stumbles, and false starts followed by a restart;
- an incomplete sentence immediately restated.

A sentence that introduces new information is NOT a retake, even if it repeats
topic words. Never discard unique content.

For each group, choose the keeper:
- Prefer the last complete, clean attempt.
- If the last attempt is incomplete or visibly broken, keep the best earlier
  complete attempt.
- `keep` must be non-empty and `discard` must be non-empty.
- Never put the same id in both lists.

Return only one JSON object:
{"groups":[{"keep":[3],"discard":[1,2],"reason":"restarted the same sentence"}],"reasoning":"short"}
Only use ids from the transcript array. Context lines are for reading only; do
not include context ids in keep or discard.
Ignore non-speech, ellipsis-only, watermark, and subtitle-credit lines.
Strictness: {strictness}
Transcript (id|start_sec|end_sec|text):
"""


def cluster_similar_repetitions(
    sentences: Sequence[Sentence],
    *,
    strategy: Strategy = "keep_last",
    max_gap_seconds: float = 300.0,
    min_similarity: float = 0.62,
) -> tuple[RetakeGroup, ...]:
    """Group nearby near-duplicate sentences, including small word swaps."""

    rate = 48000
    ordered = sorted(sentences, key=lambda item: (item.start_sample, item.end_sample, item.id))
    used: set[int] = set()
    groups: list[RetakeGroup] = []
    for index, sentence in enumerate(ordered):
        if sentence.id in used or _ELLIPSIS.match(sentence.text.strip()):
            continue
        group = [sentence]
        cursor = index + 1
        while cursor < len(ordered):
            candidate = ordered[cursor]
            if candidate.start_sample - sentence.start_sample > max_gap_seconds * rate:
                break
            if candidate.id in used:
                cursor += 1
                continue
            exact = _normalized(sentence.text) == _normalized(candidate.text)
            fuzzy = (
                _has_content(sentence)
                and _has_content(candidate)
                and _similarity(sentence, candidate) >= min_similarity
            )
            if exact or fuzzy:
                group.append(candidate)
            cursor += 1
        if len(group) < 2:
            continue
        for item in group:
            used.add(item.id)
        exact_group = len({_normalized(item.text) for item in group}) == 1
        if exact_group:
            keep = max(
                (item.id for item in group),
                key=lambda identifier: (
                    next(item.start_sample for item in group if item.id == identifier),
                    identifier,
                ),
            )
        else:
            keep = _keeper(
                [item.id for item in group],
                {item.id: item for item in group},
                strategy,
            )
        discard = tuple(item.id for item in group if item.id != keep)
        keep_sentence = next(item for item in group if item.id == keep)
        discarded = [item for item in group if item.id != keep]
        groups.append(
            RetakeGroup(
                keep=(keep,),
                discard=discard,
                reason="near-duplicate passage",
                keep_text=(keep_sentence.text,),
                discard_text=tuple(item.text for item in discarded),
                start_sec=round(min(item.start_sample for item in group) / 48000, 3),
                end_sec=round(max(item.end_sample for item in group) / 48000, 3),
            )
        )
    return tuple(groups)


def _parse_groups(
    raw: dict[str, object],
    allowed: set[int],
    sentences: dict[int, Sentence],
) -> tuple[list[RetakeGroup], list[int]]:
    """Parse group-shaped output, accepting the legacy flat discard list."""

    unknown: list[int] = []
    groups: list[RetakeGroup] = []
    raw_groups = raw.get("groups") if isinstance(raw, dict) else None
    if isinstance(raw_groups, list):
        for item in raw_groups:
            if not isinstance(item, dict):
                continue
            keep: list[int] = []
            discard: list[int] = []
            for key, target in (("keep", keep), ("discard", discard)):
                values = item.get(key)
                if not isinstance(values, list):
                    continue
                for value in values:
                    try:
                        identifier = int(value)
                    except (TypeError, ValueError):
                        continue
                    if identifier not in allowed:
                        unknown.append(identifier)
                        continue
                    if identifier not in target:
                        target.append(identifier)
            discard = [identifier for identifier in discard if identifier not in keep]
            if keep and discard:
                groups.append(
                    RetakeGroup(
                        keep=tuple(sorted(keep)),
                        discard=tuple(sorted(discard)),
                        reason=str(item.get("reason") or ""),
                    )
                )
        return groups, unknown

    # Legacy flat list: pair every discard with the closest similar keeper.
    legacy = raw.get("discard_sentence_ids") if isinstance(raw, dict) else None
    if isinstance(legacy, list):
        for value in legacy:
            try:
                identifier = int(value)
            except (TypeError, ValueError):
                continue
            if identifier not in allowed:
                unknown.append(identifier)
                continue
            source = sentences.get(identifier)
            if source is None:
                continue
            candidates = [
                item
                for item in sentences.values()
                if item.id != identifier
                and abs(item.start_sample - source.start_sample) <= 90 * 48000
            ]
            keep = (
                max(
                    candidates,
                    key=lambda item: (_similarity(source, item), item.start_sample),
                )
                if candidates
                else None
            )
            if keep is None:
                continue
            groups.append(
                RetakeGroup(
                    keep=(keep.id,),
                    discard=(identifier,),
                    reason="legacy flat discard paired with the closest take",
                )
            )
    return groups, unknown


def _merge_groups(groups: Sequence[RetakeGroup]) -> list[RetakeGroup]:
    """Merge groups that share ids; a keep always wins over a discard."""

    merged: list[RetakeGroup] = []
    for group in groups:
        current = group
        remaining: list[RetakeGroup] = []
        for existing in merged:
            if set(existing.keep) & set(current.keep + current.discard) or set(
                existing.discard
            ) & set(current.keep + current.discard):
                current = RetakeGroup(
                    keep=tuple(sorted(set(existing.keep) | set(current.keep))),
                    discard=tuple(
                        sorted(
                            (set(existing.discard) | set(current.discard))
                            - set(existing.keep)
                            - set(current.keep)
                        )
                    ),
                    reason="; ".join(filter(None, (existing.reason, current.reason))),
                )
            else:
                remaining.append(existing)
        merged = remaining + [current]
    result: list[RetakeGroup] = []
    for group in merged:
        if not group.keep or not group.discard:
            continue
        result.append(group)
    return result


def _valid_groups(
    groups: Sequence[RetakeGroup],
    sentences: dict[int, Sentence],
    *,
    max_group_span_seconds: float,
) -> list[RetakeGroup]:
    valid: list[RetakeGroup] = []
    rate = 48000
    for group in groups:
        ids = group.keep + group.discard
        if len(ids) < 2 or not group.keep or not group.discard:
            continue
        if any(identifier not in sentences for identifier in ids):
            continue
        times = [sentences[identifier].start_sample for identifier in ids]
        ends = [sentences[identifier].end_sample for identifier in ids]
        if (max(ends) - min(times)) / rate > max_group_span_seconds:
            continue
        valid.append(group)
    return valid


def _prompt(
    sentences: Sequence[Sentence],
    strictness: str,
    before: Sequence[Sentence] = (),
    after: Sequence[Sentence] = (),
) -> str:
    rules = _STRICTNESS_RULES.get(strictness, _STRICTNESS_RULES["balanced"])
    lines: list[str] = []
    for item in before:
        lines.append(
            f"[context] {item.id}|{item.start_sample / 48000:.2f}|"
            f"{item.end_sample / 48000:.2f}|{item.text}"
        )
    for item in sentences:
        lines.append(
            f"{item.id}|{item.start_sample / 48000:.2f}|{item.end_sample / 48000:.2f}|{item.text}"
        )
    for item in after:
        lines.append(
            f"[context] {item.id}|{item.start_sample / 48000:.2f}|"
            f"{item.end_sample / 48000:.2f}|{item.text}"
        )
    return PROMPT_HEADER.replace("{strictness}", f"{strictness} — {rules}") + "\n".join(lines)


def _chunks(
    sentences: Sequence[Sentence],
    *,
    single_pass: bool,
    context_window: int,
    max_chars: int = 30_000,
) -> list[tuple[list[Sentence], list[Sentence], list[Sentence]]]:
    ordered = list(sentences)
    if single_pass:
        rough = sum(len(item.text) + 32 for item in ordered)
        if rough <= max_chars:
            return [(ordered, [], [])]
    size = max(1, context_window)
    stride = max(1, size // 2)
    chunks: list[tuple[list[Sentence], list[Sentence], list[Sentence]]] = []
    for start in range(0, len(ordered), stride):
        chunk = ordered[start : start + size]
        if not chunk:
            break
        before = ordered[max(0, start - 2) : start]
        after = ordered[start + size : start + size + 2]
        chunks.append((chunk, before, after))
        if start + size >= len(ordered):
            break
    return chunks


def _windows(sentences: Sequence[Sentence], size: int) -> list[list[Sentence]]:
    """Backward-compatible sentence windows for callers and tests."""

    return [
        chunk
        for chunk, _before, _after in _chunks(
            sentences,
            single_pass=False,
            context_window=max(1, size),
        )
    ]


def _apply_strategy(
    groups: Sequence[RetakeGroup],
    sentences: dict[int, Sentence],
    strategy: Strategy,
) -> list[RetakeGroup]:
    """Keep the LLM keeper when it is valid; infer one only for empty groups."""

    adjusted: list[RetakeGroup] = []
    for group in groups:
        candidates = [
            identifier
            for identifier in dict.fromkeys(group.keep + group.discard)
            if identifier in sentences
        ]
        if not candidates:
            continue
        ordered = sorted(candidates, key=lambda item: (sentences[item].start_sample, item))
        keeper = _choose_keeper(ordered, sentences, strategy)
        keep = [keeper]
        discard = [identifier for identifier in ordered if identifier != keeper]
        # Sponsor/CTA and unique facts must survive even when the model grouped
        # them with a similar retake.
        for identifier in list(discard):
            if _unique_facts(sentences[identifier], sentences[keeper]):
                keep.append(identifier)
                discard.remove(identifier)
        if not discard:
            continue
        keep_sentences = [sentences[identifier] for identifier in sorted(keep)]
        discard_sentences = [sentences[identifier] for identifier in sorted(discard)]
        all_sentences = keep_sentences + discard_sentences
        adjusted.append(
            RetakeGroup(
                keep=tuple(sorted(keep)),
                discard=tuple(sorted(discard)),
                reason=group.reason,
                keep_text=tuple(item.text for item in keep_sentences),
                discard_text=tuple(item.text for item in discard_sentences),
                start_sec=round(
                    min(item.start_sample for item in all_sentences) / 48000, 3
                ),
                end_sec=round(
                    max(item.end_sample for item in all_sentences) / 48000, 3
                ),
            )
        )
    return adjusted

