from __future__ import annotations

from videoflow.application.boundaries import enforce_word_integrity
from videoflow.domain.state import Sentence, WordTiming


def _sentence(identifier: int, start: int, end: int) -> Sentence:
    return Sentence(
        id=identifier,
        start_sample=start,
        end_sample=end,
        text="extraordinariamente",
        words=[
            WordTiming(
                word="extraordinariamente",
                start_sample=start,
                end_sample=end,
                probability=1.0,
            )
        ],
    )


def test_split_word_is_merged_when_the_gap_is_small() -> None:
    sentence = _sentence(0, 1000, 1400)
    spans, violations = enforce_word_integrity(
        [(900, 1200), (1300, 1600)],
        [sentence],
        set(),
        sample_rate=1000,
        max_gap_ms=500,
    )
    assert violations == []
    assert spans == [(900, 1600)]


def test_word_removed_by_a_cut_is_not_required() -> None:
    sentence = _sentence(0, 1000, 1400)
    spans, violations = enforce_word_integrity(
        [(900, 1200)],
        [sentence],
        set(),
        removed_spans=[(1000, 1400)],
        sample_rate=1000,
        max_gap_ms=500,
    )
    assert violations == []
    assert spans == [(900, 1200)]


def test_large_gap_is_reported_instead_of_adding_audio() -> None:
    sentence = _sentence(0, 1000, 2200)
    spans, violations = enforce_word_integrity(
        [(900, 1200), (1800, 2400)],
        [sentence],
        set(),
        sample_rate=1000,
        max_gap_ms=500,
    )
    assert spans == [(900, 1200), (1800, 2400)]
    assert len(violations) == 1
