"""Retake culling orchestration."""

from __future__ import annotations

from collections.abc import Sequence

from videoflow.adapters import LlmClient
from videoflow.application.retake_spans import (  # noqa: F401 - re-exported
    cull_intervals,
    inactive_spans_for_discards,
    snap_cuts_to_silence,
    subtract_spans,
)
from videoflow.application.retakes.clustering import (
    _apply_strategy,
    _chunks,
    _merge_groups,
    _parse_groups,
    _prompt,
    _valid_groups,
    cluster_similar_repetitions,
)
from videoflow.application.retakes.guards import (
    _group_for,
    _guard_unique_discards,
    _reconcile_groups,
)
from videoflow.application.retakes.models import RetakeGroup, RetakeResult
from videoflow.application.retakes.similarity import (
    _content_tokens,
    _hallucination_loop,
    _keeper,
    _similarity,
    _watermark_only,
)
from videoflow.application.spans import merge_spans
from videoflow.application.takes import (
    select_duplicate_takes,
    semantic_duplicate_sentences,
)
from videoflow.domain.retakes import (
    GuardResult,
    Strategy,
    apply_retake_guard,
    cluster_exact_repetitions,
)
from videoflow.domain.state import Sentence


def cull_retakes(
    sentences: Sequence[Sentence],
    *,
    client: LlmClient | None = None,
    strategy: Strategy = "keep_last",
    context_window: int = 15,
    strictness: str = "balanced",
    single_pass: bool = True,
    max_group_span_seconds: float = 180.0,
    max_discard_ratio: float = 0.45,
    semantic_duplicates: bool = False,
) -> RetakeResult:
    if not sentences:
        return RetakeResult((), (), "", 0, ())
    order = {item.id: item for item in sentences}
    proposed: list[RetakeGroup] = []
    proposed_discard: set[int] = set()
    notes: list[str] = []
    chunks = _chunks(
        sentences,
        single_pass=single_pass,
        context_window=max(1, context_window),
    )
    windows = len(chunks) if client is not None else 0
    if client is not None:
        for chunk, before, after in chunks:
            raw = client.complete_json(
                _prompt(chunk, strictness, before, after),
                "videoflow.retakes",
            )
            parsed, unknown = _parse_groups(
                raw,
                {item.id for item in chunk},
                {item.id: item for item in chunk},
            )
            if unknown:
                notes.append(f"ignored unknown retake ids: {sorted(set(unknown))}")
            proposed.extend(parsed)
            proposed_discard.update(identifier for group in parsed for identifier in group.discard)
            if isinstance(raw, dict):
                reasoning = raw.get("reasoning")
                if reasoning:
                    notes.append(str(reasoning))
    groups = _merge_groups(proposed)
    groups = _valid_groups(
        groups,
        order,
        max_group_span_seconds=max_group_span_seconds,
    )
    groups = _apply_strategy(groups, order, strategy)
    groups, unique_restored = _guard_unique_discards(groups)
    if unique_restored:
        notes.append(
            f"restored {unique_restored} unique-looking sentence(s) from over-grouping"
        )

    if not groups:
        if proposed:
            notes.append(
                "LLM groups were rejected or restored; kept the content instead "
                "of falling back to near-duplicate matching"
            )
        else:
            groups = list(cluster_similar_repetitions(sentences, strategy=strategy))

    discard = {identifier for group in groups for identifier in group.discard}
    keepers = {identifier for group in groups for identifier in group.keep}
    discard -= keepers
    if len(discard) > max(1, int(len(sentences) * max_discard_ratio)):
        notes.append("retake proposal exceeded the discard budget; kept only near-duplicate groups")
        groups = list(cluster_similar_repetitions(sentences, strategy=strategy))
        groups = _apply_strategy(groups, order, strategy)
        groups, _ = _guard_unique_discards(groups)
        discard = {identifier for group in groups for identifier in group.discard}
        keepers = {identifier for group in groups for identifier in group.keep}
        discard -= keepers

    # Never delete a sentence whose content words appear nowhere in the kept
    # transcript. This is the last line of defence against the LLM grouping a
    # meaningful sentence with a retake.
    global_restored: set[int] = set()
    group_keeper: dict[int, int] = {}
    for group in groups:
        if not group.keep:
            continue
        for identifier in group.discard:
            group_keeper.setdefault(identifier, group.keep[0])
    kept_ids = {item.id for item in sentences} - discard
    kept_tokens: set[str] = set()
    for item in sentences:
        if item.id in kept_ids:
            kept_tokens.update(_content_tokens(item.text))
    for identifier in sorted(discard):
        item = order[identifier]
        if len(item.text.split()) < 4:
            continue
        keeper_id = group_keeper.get(identifier)
        keeper_sentence = order.get(keeper_id) if keeper_id is not None else None
        if keeper_sentence is None or _similarity(item, keeper_sentence) >= 0.65:
            continue
        unique = _content_tokens(item.text) - kept_tokens
        if not unique:
            continue
        discard.remove(identifier)
        kept_ids.add(identifier)
        kept_tokens.update(_content_tokens(item.text))
        global_restored.add(identifier)
    if global_restored:
        notes.append(
            f"restored {len(global_restored)} sentence(s) with unique content words"
        )

    # Exact repeats are unambiguous: keep the last/best sentence and remove
    # the earlier identical ones even when the LLM kept both. An identical
    # line repeated four or more times at a regular interval is an ASR loop,
    # not speech: the whole loop is removed.
    clusters = cluster_exact_repetitions([(item.id, item.text) for item in sentences])
    loop_ids: set[int] = set()
    loop_clusters: set[int] = set()
    for index, cluster in enumerate(clusters):
        if _hallucination_loop(cluster.sentence_ids, order):
            loop_ids.update(cluster.sentence_ids)
            loop_clusters.add(index)
    watermark_ids = {
        item.id for item in sentences if _watermark_only(item.text)
    }
    for index, cluster in enumerate(clusters):
        if index in loop_clusters:
            continue
        keeper = _keeper(cluster.sentence_ids, order, strategy)
        discard.update(
            identifier
            for identifier in cluster.sentence_ids
            if identifier != keeper
        )
    guarded: GuardResult = apply_retake_guard(
        sorted(discard - loop_ids - watermark_ids),
        clusters=[
            cluster
            for index, cluster in enumerate(clusters)
            if index not in loop_clusters
        ],
        valid_ids=[item.id for item in sentences],
        strategy=strategy,
    )
    discard = set(guarded.discard_sentence_ids)
    discard.update(loop_ids)
    discard.update(watermark_ids)
    restored = set(guarded.restored_sentence_ids)
    restored.update(proposed_discard - discard)
    restored.update(global_restored)
    restored -= loop_ids | watermark_ids
    # A watermark sentence must never be the keeper of real content.
    for group in groups:
        if not (set(group.keep) & watermark_ids):
            continue
        for identifier in group.discard:
            if identifier in watermark_ids or identifier in loop_ids:
                continue
            if identifier in discard:
                discard.discard(identifier)
                restored.add(identifier)
    groups = _reconcile_groups(groups, discard)
    for index, cluster in enumerate(clusters):
        if index in loop_clusters:
            continue
        keeper = _keeper(cluster.sentence_ids, order, strategy)
        removed = tuple(
            identifier
            for identifier in cluster.sentence_ids
            if identifier != keeper and identifier in discard
        )
        if not removed:
            continue
        if any(set(group.discard) == set(removed) for group in groups):
            continue
        groups.append(_group_for(order, (keeper,), removed, "exact repeat"))
    if semantic_duplicates:
        semantic_ids = semantic_duplicate_sentences(sentences, discard)
        if semantic_ids:
            discard.update(semantic_ids)
            restored -= semantic_ids
            notes.append(
                f"removed {len(semantic_ids)} semantic duplicate sentence(s)"
            )
    kept_sentences = [item for item in sentences if item.id not in discard]
    take_groups = select_duplicate_takes(kept_sentences)
    if take_groups:
        existing_keepers = {identifier for group in groups for identifier in group.keep}
        for take_group in take_groups:
            remove = tuple(
                identifier
                for identifier in take_group.discard
                if identifier not in existing_keepers
                and identifier not in restored
            )
            if not remove:
                continue
            discard.update(remove)
            groups.append(
                RetakeGroup(
                    keep=take_group.keep,
                    discard=remove,
                    reason=take_group.reason,
                    keep_text=take_group.keep_text,
                    discard_text=take_group.discard_text,
                    start_sec=take_group.start_sec,
                    end_sec=take_group.end_sec,
                )
            )
        notes.append(f"grouped {len(take_groups)} duplicate take(s)")
    for index in sorted(loop_clusters):
        cluster = clusters[index]
        groups.append(
            _group_for(order, (), tuple(cluster.sentence_ids), "repeated ASR loop")
        )
    credit_ids = watermark_ids - loop_ids
    if credit_ids:
        groups.append(
            _group_for(order, (), tuple(sorted(credit_ids)), "watermark credit")
        )
    if loop_ids:
        notes.append(f"removed {len(loop_ids)} sentence(s) from repeated ASR loops")
    if watermark_ids:
        notes.append(f"removed {len(watermark_ids)} watermark credit(s)")
    if not notes:
        notes.append("no retake groups")
    return RetakeResult(
        discard_sentence_ids=tuple(sorted(discard)),
        restored_sentence_ids=tuple(sorted(restored)),
        reasoning="; ".join(dict.fromkeys(notes)),
        windows=windows,
        groups=tuple(groups),
    )


_merge = merge_spans
