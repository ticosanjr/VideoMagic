"""Transcript-driven retake culling.

The LLM proposes *groups* of attempts: one keeper and the failed attempts.
The domain validates ids, merges groups, keeps at least one sentence per group,
and restores any discard that was not part of a valid group. Without a client,
near-duplicate text is still culled deterministically.

Retakes are semantic, not exact: the speaker often repeats the same idea with a
few different words. A flat discard list cannot express that safely, so the
LLM output is intentionally group-shaped and the deterministic layer is a guard
rather than the primary decision maker.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from videoflow.adapters import LlmClient
from videoflow.domain.retakes import (
    GuardResult,
    Strategy,
    apply_retake_guard,
    cluster_exact_repetitions,
    normalize_sentence_text,
)
from videoflow.domain.state import InactiveSpan, Sentence

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

_STRICTNESS_RULES = {
    "conservative": (
        "Only discard attempts that clearly repeat the same passage. "
        "When in doubt, keep the sentence."
    ),
    "balanced": (
        "Discard clear retakes and aborted starts. Keep new information and ambiguous sentences."
    ),
    "aggressive": (
        "Also discard incomplete or stumbled sentences when the next sentence "
        "restates them. Still never discard unique content."
    ),
}

_ELLIPSIS = re.compile(r"^[\s.…!?;:,-]*$")
_WATERMARK = re.compile(
    r"legendas?\s+pela\s+comunidade|amara\.org|subtitles?\s+by|"
    r"legendado\s+por|transcri(?:ção|cao)\s+por",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class RetakeGroup:
    """One repeated passage: the keeper and the attempts to remove."""

    keep: tuple[int, ...]
    discard: tuple[int, ...]
    reason: str = ""
    keep_text: tuple[str, ...] = ()
    discard_text: tuple[str, ...] = ()
    start_sec: float = 0.0
    end_sec: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "keep": list(self.keep),
            "discard": list(self.discard),
            "reason": self.reason,
            "keep_text": list(self.keep_text),
            "discard_text": list(self.discard_text),
            "start_sec": self.start_sec,
            "end_sec": self.end_sec,
        }


@dataclass(frozen=True, slots=True)
class RetakeResult:
    discard_sentence_ids: tuple[int, ...]
    restored_sentence_ids: tuple[int, ...]
    reasoning: str
    windows: int
    groups: tuple[RetakeGroup, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "discard_sentence_ids": list(self.discard_sentence_ids),
            "restored_sentence_ids": list(self.restored_sentence_ids),
            "reasoning": self.reasoning,
            "windows": self.windows,
            "groups": [group.to_dict() for group in self.groups],
        }


def _normalized(text: str) -> str:
    return normalize_sentence_text(text)


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9à-ÿ]+", text.casefold())
        if len(token) > 2 or token.isdigit()
    }


def _similarity(left: Sentence, right: Sentence) -> float:
    a = _normalized(left.text)
    b = _normalized(right.text)
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    left_tokens = _tokens(left.text)
    right_tokens = _tokens(right.text)
    if not left_tokens or not right_tokens:
        return ratio
    different = left_tokens ^ right_tokens
    if different and all(token.isdigit() for token in different):
        # "Chapter 1" / "Chapter 2" are list items, not retakes.
        return 0.0
    overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    shorter = min(len(left_tokens), len(right_tokens))
    longer = max(len(left_tokens), len(right_tokens))
    length_ratio = shorter / longer
    return max(ratio, overlap) if length_ratio >= 0.45 else ratio * length_ratio


def _has_content(sentence: Sentence) -> bool:
    return len(_tokens(sentence.text)) >= 3 and len(sentence.text.split()) >= 4


def _complete(sentence: Sentence) -> bool:
    text = sentence.text.strip()
    if not text or _ELLIPSIS.match(text) or _WATERMARK.search(text):
        return False
    return text.endswith((".", "!", "?")) or len(_tokens(text)) >= 4


def _completeness(sentence: Sentence) -> float:
    text = sentence.text.strip()
    score = 0.0
    if text.endswith((".", "!", "?")):
        score += 0.35
    score += min(len(_tokens(text)) / 12.0, 0.35)
    if sentence.words:
        probabilities = [word.probability for word in sentence.words]
        score += min(sum(probabilities) / len(probabilities), 1.0) * 0.3
    return round(score, 6)


def _keeper(group: Sequence[int], sentences: dict[int, Sentence], strategy: Strategy) -> int:
    ordered = [item for item in group if item in sentences]
    if not ordered:
        raise ValueError("retake group has no valid sentences")
    if strategy == "keep_best":
        return max(ordered, key=lambda item: (_completeness(sentences[item]), item))
    last = max(ordered, key=lambda item: (sentences[item].start_sample, item))
    if _complete(sentences[last]):
        return last
    complete = [item for item in ordered if _complete(sentences[item])]
    if complete:
        return max(complete, key=lambda item: (sentences[item].start_sample, item))
    return last


def cluster_similar_repetitions(
    sentences: Sequence[Sentence],
    *,
    strategy: Strategy = "keep_last",
    max_gap_seconds: float = 90.0,
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
            keep = max(
                candidates,
                key=lambda item: (_similarity(source, item), item.start_sample),
                default=None,
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
        keep = [identifier for identifier in group.keep if identifier in sentences]
        discard = [
            identifier
            for identifier in group.discard
            if identifier in sentences and identifier not in keep
        ]
        if not keep:
            candidates = list(dict.fromkeys(group.keep + group.discard))
            if not candidates:
                continue
            keep = [_keeper(candidates, sentences, strategy)]
            discard = [identifier for identifier in candidates if identifier not in keep]
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

    # The exact-repeat guard protects the keeper of unambiguous retakes even
    # when the LLM grouped the passage differently.
    clusters = cluster_exact_repetitions([(item.id, item.text) for item in sentences])
    guarded: GuardResult = apply_retake_guard(
        sorted(discard),
        clusters=clusters,
        valid_ids=[item.id for item in sentences],
        strategy=strategy,
    )
    discard = set(guarded.discard_sentence_ids)
    restored = set(guarded.restored_sentence_ids)
    restored.update(proposed_discard - discard)
    groups = _reconcile_groups(groups, discard)
    if not notes:
        notes.append("no retake groups")
    return RetakeResult(
        discard_sentence_ids=tuple(sorted(discard)),
        restored_sentence_ids=tuple(sorted(restored)),
        reasoning="; ".join(dict.fromkeys(notes)),
        windows=windows,
        groups=tuple(groups),
    )


def snap_cuts_to_silence(
    cuts: Sequence[tuple[int, int]],
    silence_spans: Sequence[InactiveSpan],
    *,
    sample_rate: int = 48000,
    search_ms: int = 400,
) -> tuple[list[tuple[int, int]], int]:
    """Move cut edges into nearby silence so kept words are not clipped.

    The cut start moves forward to the next silence onset and the cut end moves
    backward to the previous silence end. That keeps the words on both kept
    sides intact; a small residue of the discarded take is safer than cutting a
    word in half.
    """

    if not cuts or not silence_spans:
        return list(cuts), 0
    search = max(1, (search_ms * sample_rate + 500) // 1000)
    silences = sorted(
        (span.start_sample, span.end_sample) for span in silence_spans
    )
    snapped = 0
    output: list[tuple[int, int]] = []
    for start, end in cuts:
        new_start = start
        new_end = end
        for silence_start, _silence_end in silences:
            if silence_start >= start and silence_start - start <= search:
                if silence_start < end:
                    new_start = silence_start
                break
        for _silence_start, silence_end in reversed(silences):
            if silence_end <= end and end - silence_end <= search:
                if silence_end > start:
                    new_end = silence_end
                break
        if new_start != start or new_end != end:
            snapped += 1
        if new_end > new_start:
            output.append((new_start, new_end))
    return _merge(output), snapped


def cull_intervals(
    sentences: Sequence[Sentence],
    discard_sentence_ids: Sequence[int],
) -> list[tuple[int, int]]:
    discard = set(discard_sentence_ids)
    return sorted(
        (item.start_sample, item.end_sample)
        for item in sentences
        if item.id in discard and item.end_sample > item.start_sample
    )


def inactive_spans_for_discards(
    sentences: Sequence[Sentence],
    discard_sentence_ids: Sequence[int],
    *,
    manual_ids: Sequence[int] = (),
) -> list[InactiveSpan]:
    """Map discarded sentences to typed source spans for the Recut timeline."""

    discard = set(discard_sentence_ids)
    manual = set(manual_ids)
    spans = [
        InactiveSpan(
            start_sample=item.start_sample,
            end_sample=item.end_sample,
            reason="manual" if item.id in manual else "retake",
        )
        for item in sentences
        if item.id in discard and item.end_sample > item.start_sample
    ]
    return sorted(spans, key=lambda span: (span.start_sample, span.end_sample))


def subtract_spans(
    speech: Sequence[tuple[int, int]],
    cuts: Sequence[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Remove cut intervals from speech spans, merging the remainder."""

    if not cuts:
        return _merge(speech)
    merged_cuts = _merge(cuts)
    output: list[tuple[int, int]] = []
    for start, end in speech:
        pieces = [(start, end)]
        for cut_start, cut_end in merged_cuts:
            next_pieces: list[tuple[int, int]] = []
            for piece_start, piece_end in pieces:
                if cut_end <= piece_start or cut_start >= piece_end:
                    next_pieces.append((piece_start, piece_end))
                    continue
                if piece_start < cut_start:
                    next_pieces.append((piece_start, cut_start))
                if cut_end < piece_end:
                    next_pieces.append((cut_end, piece_end))
            pieces = next_pieces
        output.extend(pieces)
    return _merge(output)


def _merge(spans: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    ordered = sorted((start, end) for start, end in spans if end > start)
    merged: list[tuple[int, int]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
