"""Source-span helpers for retake culling and timeline subtraction."""

from __future__ import annotations

from collections.abc import Sequence

from videoflow.application.spans import merge_spans
from videoflow.domain.state import InactiveSpan, Sentence


def snap_cuts_to_silence(
    cuts: Sequence[tuple[int, int]],
    silence_spans: Sequence[InactiveSpan],
    *,
    sample_rate: int = 48000,
    search_ms: int = 400,
) -> tuple[list[tuple[int, int]], int]:
    """Move cut edges into nearby silence so kept words are not clipped."""

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
    return merge_spans(output), snapped


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
        return merge_spans(speech)
    merged_cuts = merge_spans(cuts)
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
    return merge_spans(output)
