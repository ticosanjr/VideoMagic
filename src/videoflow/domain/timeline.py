"""Timeline continuity checks. Spans are ``[start, end)`` in one time unit."""

from __future__ import annotations

from collections.abc import Sequence


def find_overlaps(spans: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Return index pairs of spans that overlap. Touching edges do not overlap."""

    ordered = sorted(enumerate(spans), key=lambda item: (item[1][0], item[1][1], item[0]))
    overlaps: list[tuple[int, int]] = []
    for position, (left_index, (left_start, left_end)) in enumerate(ordered):
        if left_end < left_start:
            raise ValueError("inverted span")
        for right_index, (right_start, right_end) in ordered[position + 1 :]:
            if right_start >= left_end:
                break
            if right_end < right_start:
                raise ValueError("inverted span")
            if right_start < left_end and left_start < right_end:
                pair = (
                    (left_index, right_index)
                    if left_index < right_index
                    else (right_index, left_index)
                )
                overlaps.append(pair)
    return overlaps


def is_packed(spans: Sequence[tuple[int, int]], *, origin: int = 0) -> bool:
    """True when spans are contiguous from ``origin`` with no gaps or overlaps."""

    if not spans:
        return True
    ordered = sorted(spans, key=lambda item: item[0])
    if ordered[0][0] != origin:
        return False
    cursor = origin
    for start, end in ordered:
        if end < start or start != cursor:
            return False
        cursor = end
    return True
