"""Transcript-driven retake culling.

The LLM proposes discards per window. The domain validates ids, clusters exact
repeats, and the keeper guard restores a final take the model tried to drop.
Without a client, exact repeated text is still culled deterministically.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from videoflow.adapters import LlmClient
from videoflow.domain.retakes import (
    GuardResult,
    Strategy,
    apply_retake_guard,
    cluster_exact_repetitions,
)
from videoflow.domain.state import LlmRetakeResponse, Sentence

PROMPT_HEADER = """\
Remove failed takes from this transcript.
Rules:
- Keep the last complete attempt of a repeated passage.
- Discard aborted starts, stumbles, and earlier attempts.
- Only use ids from the array below.
- Return only JSON matching:
  {"discard_sentence_ids": [ints], "reasoning": "short explanation"}
Strictness: {strictness}
Sentences:
"""


@dataclass(frozen=True, slots=True)
class RetakeResult:
    discard_sentence_ids: tuple[int, ...]
    restored_sentence_ids: tuple[int, ...]
    reasoning: str
    windows: int

    def to_dict(self) -> dict[str, object]:
        return {
            "discard_sentence_ids": list(self.discard_sentence_ids),
            "restored_sentence_ids": list(self.restored_sentence_ids),
            "reasoning": self.reasoning,
            "windows": self.windows,
        }


def cull_retakes(
    sentences: Sequence[Sentence],
    *,
    client: LlmClient | None = None,
    strategy: Strategy = "keep_last",
    context_window: int = 15,
    strictness: str = "balanced",
) -> RetakeResult:
    if not sentences:
        return RetakeResult((), (), "", 0)
    window = max(1, context_window)
    proposed: set[int] = set()
    notes: list[str] = []
    windows = 0
    if client is not None:
        for chunk in _windows(sentences, window):
            prompt = _prompt(chunk, strictness)
            raw = client.complete_json(prompt, "videoflow.retakes")
            response = LlmRetakeResponse.model_validate(raw)
            allowed = {item.id for item in chunk}
            unknown = [item for item in response.discard_sentence_ids if item not in allowed]
            if unknown:
                from videoflow.domain.errors import InvalidRetakeIdsError

                raise InvalidRetakeIdsError(unknown)
            proposed.update(response.discard_sentence_ids)
            notes.append(response.reasoning)
            windows += 1

    clusters = cluster_exact_repetitions([(item.id, item.text) for item in sentences])
    if client is None:
        for cluster in clusters:
            proposed.update(cluster.sentence_ids[:-1])

    guarded: GuardResult = apply_retake_guard(
        sorted(proposed),
        clusters=clusters,
        valid_ids=[item.id for item in sentences],
        strategy=strategy,
    )
    reasoning = "; ".join(dict.fromkeys(notes)) if notes else "exact repeats only"
    return RetakeResult(
        discard_sentence_ids=guarded.discard_sentence_ids,
        restored_sentence_ids=guarded.restored_sentence_ids,
        reasoning=reasoning,
        windows=windows,
    )


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


def _windows(sentences: Sequence[Sentence], size: int) -> list[list[Sentence]]:
    if len(sentences) <= size:
        return [list(sentences)]
    stride = max(1, size // 2)
    chunks: list[list[Sentence]] = []
    for start in range(0, len(sentences), stride):
        chunk = list(sentences[start : start + size])
        if not chunk:
            break
        chunks.append(chunk)
        if start + size >= len(sentences):
            break
    return chunks


def _prompt(sentences: Sequence[Sentence], strictness: str) -> str:
    payload = [{"id": item.id, "text": item.text} for item in sentences]
    return PROMPT_HEADER.replace("{strictness}", strictness) + json.dumps(
        payload, ensure_ascii=False
    )
