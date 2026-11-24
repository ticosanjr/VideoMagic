"""Retake grouping, merging, validation, and chunking."""

from __future__ import annotations

from collections.abc import Sequence

from videoflow.application.retakes.models import RetakeGroup
from videoflow.application.retakes.similarity import (
    _STRICTNESS_RULES,
    _choose_keeper,
    _similarity,
    _unique_facts,
)
from videoflow.core.media_contract.constants import AUDIO_MASTER_RATE
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
    max_gap_seconds: float = 420.0,
    min_similarity: float = 0.58,
    max_group_span_seconds: float = 420.0,
    max_window_sentences: int = 25,
    max_discard_ratio: float = 0.75,
) -> tuple[RetakeGroup, ...]:
    """Group nearby and distant near-duplicate sentences transitively."""

    from videoflow.application.decupage.retake_cluster import cluster_distant_retakes

    ordered = sorted(sentences, key=lambda item: (item.start_sample, item.end_sample, item.id))
    by_id = {item.id: item for item in ordered}
    groups: list[RetakeGroup] = []
    for cluster in cluster_distant_retakes(
        ordered,
        max_window_sentences=max_window_sentences,
        max_gap_sec=max_gap_seconds,
        strategy=strategy,
        min_similarity=min_similarity,
        max_discard_ratio=max_discard_ratio,
    ):
        keeper = by_id.get(cluster.keeper_id)
        discarded = [by_id[item] for item in cluster.discard_ids if item in by_id]
        if keeper is None or not discarded:
            continue
        times = [keeper.start_sample, *(item.start_sample for item in discarded)]
        ends = [keeper.end_sample, *(item.end_sample for item in discarded)]
        groups.append(
            RetakeGroup(
                keep=(keeper.id,),
                discard=tuple(item.id for item in discarded),
                reason=cluster.reason,
                keep_text=(keeper.text,),
                discard_text=tuple(item.text for item in discarded),
                start_sec=round(min(times) / AUDIO_MASTER_RATE, 3),
                end_sec=round(max(ends) / AUDIO_MASTER_RATE, 3),
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
                and abs(item.start_sample - source.start_sample) <= 90 * AUDIO_MASTER_RATE
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
    rate = AUDIO_MASTER_RATE
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
            f"[context] {item.id}|{item.start_sample / AUDIO_MASTER_RATE:.2f}|"
            f"{item.end_sample / AUDIO_MASTER_RATE:.2f}|{item.text}"
        )
    for item in sentences:
        lines.append(
            f"{item.id}|{item.start_sample / AUDIO_MASTER_RATE:.2f}|"
            f"{item.end_sample / AUDIO_MASTER_RATE:.2f}|{item.text}"
        )
    for item in after:
        lines.append(
            f"[context] {item.id}|{item.start_sample / AUDIO_MASTER_RATE:.2f}|"
            f"{item.end_sample / AUDIO_MASTER_RATE:.2f}|{item.text}"
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
                    min(item.start_sample for item in all_sentences) / AUDIO_MASTER_RATE, 3
                ),
                end_sec=round(
                    max(item.end_sample for item in all_sentences) / AUDIO_MASTER_RATE, 3
                ),
            )
        )
    return adjusted

