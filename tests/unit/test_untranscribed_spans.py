from __future__ import annotations

from videoflow.application.timeline_builder import (
    add_untranscribed_spans,
    transcript_spans,
)
from videoflow.domain.state import Sentence, WordTiming


def _sentence(
    identifier: int,
    *,
    start: int,
    end: int,
    rate: int = 1000,
) -> Sentence:
    return Sentence(
        id=identifier,
        start_sample=start,
        end_sample=end,
        text="palavra",
        words=[
            WordTiming(
                word="palavra",
                start_sample=start,
                end_sample=end,
                probability=1.0,
            )
        ],
    )


def test_add_untranscribed_keeps_long_speech_but_not_low_energy() -> None:
    transcript = [_sentence(0, start=100, end=200)]
    vad = [(0, 1000), (2000, 3000)]

    def rms_at(start: int, _end: int) -> int:
        return 100 if start >= 2000 else 2000

    speech = add_untranscribed_spans(
        [],
        vad,
        transcript,
        set(),
        sample_rate=1000,
        duration_samples=4000,
        min_ms=500,
        energy_threshold=1500,
        rms_at=rms_at,
    )
    assert speech == [(200, 1000)]


def test_add_untranscribed_subtracts_discarded_sentences() -> None:
    transcript = [
        _sentence(0, start=100, end=200),
        _sentence(1, start=2100, end=2900),
    ]

    def rms_at(_start: int, _end: int) -> int:
        return 2000

    speech = add_untranscribed_spans(
        [],
        [(0, 1000), (2000, 3000)],
        transcript,
        {1},
        sample_rate=1000,
        duration_samples=4000,
        min_ms=500,
        energy_threshold=1500,
        rms_at=rms_at,
    )
    assert speech == [(200, 1000)]


def test_transcript_spans_extend_head_and_tail_to_energy_valleys() -> None:
    sentence = _sentence(0, start=1000, end=1200)

    def rms_at(start: int, _end: int) -> int:
        middle = start
        if 900 <= middle < 910 or 1300 <= middle < 1310:
            return 100
        return 3000

    spans, _noise = transcript_spans(
        [sentence],
        set(),
        sample_rate=1000,
        duration_samples=2000,
        pad_before_ms=0,
        pad_after_ms=0,
        head_guard_ms=100,
        tail_guard_ms=200,
        guard_energy_threshold=1500,
        rms_at=rms_at,
    )
    assert spans == [(900, 1300)]


def test_repair_clipped_words_restores_a_word_split_by_the_cap() -> None:
    from videoflow.application.timeline_builder import repair_clipped_words

    sentence = _sentence(0, start=1000, end=1400)
    result = repair_clipped_words(
        [(800, 1200), (1300, 1600)],
        [sentence],
        set(),
        sample_rate=1000,
        max_word_ms=800,
        guard_ms=20,
    )
    assert result == [(800, 1400), (1300, 1600)] or result == [(800, 1600)]


def test_repair_clipped_words_ignores_implausibly_long_words() -> None:
    from videoflow.application.timeline_builder import repair_clipped_words

    sentence = _sentence(0, start=1000, end=1400)
    result = repair_clipped_words(
        [(800, 1200)],
        [sentence],
        set(),
        sample_rate=1000,
        max_word_ms=200,
        guard_ms=20,
    )
    assert result == [(800, 1200)]
