from __future__ import annotations

from videoflow.application.timeline_builder import transcript_spans
from videoflow.domain.state import Sentence, WordTiming

RATE = 48_000


def _word(text: str, start: float, end: float) -> WordTiming:
    return WordTiming(
        word=text,
        start_sample=round(start * RATE),
        end_sample=round(end * RATE),
        probability=0.95,
    )


def _sentence(identifier: int, *words: WordTiming) -> Sentence:
    return Sentence(
        id=identifier,
        start_sample=words[0].start_sample,
        end_sample=words[-1].end_sample,
        text=" ".join(word.word for word in words),
        words=list(words),
    )


def _leaked(spans: list[tuple[int, int]], start: float, end: float) -> float:
    low = start * RATE
    high = end * RATE
    total = 0.0
    for span_start, span_end in spans:
        left = max(low, span_start)
        right = min(high, span_end)
        if right > left:
            total += right - left
    return total / RATE


def test_short_forced_cut_is_not_swallowed_by_the_gap_rule() -> None:
    sentence = _sentence(
        0,
        _word("isso", 0.0, 0.4),
        _word("e", 0.45, 0.7),
        _word("pronto", 0.75, 1.0),
        _word("a", 1.05, 1.12),
        _word("acho", 1.14, 1.5),
    )
    spans, _noise = transcript_spans(
        [sentence],
        set(),
        sample_rate=RATE,
        duration_samples=4 * RATE,
        pad_before_ms=120,
        pad_after_ms=150,
        forced_cuts=[(round(1.05 * RATE), round(1.12 * RATE))],
    )
    assert _leaked(spans, 1.05, 1.12) < 1e-6


def test_padding_does_not_restore_a_forced_cut() -> None:
    sentence = _sentence(
        0,
        _word("isso", 0.0, 0.4),
        _word("e", 0.45, 0.7),
        _word("pronto", 0.75, 1.0),
        _word("eu", 1.0, 1.2),
        _word("acho", 1.25, 1.6),
    )
    spans, _noise = transcript_spans(
        [sentence],
        set(),
        sample_rate=RATE,
        duration_samples=4 * RATE,
        pad_before_ms=120,
        pad_after_ms=150,
        forced_cuts=[(round(1.0 * RATE), round(1.2 * RATE))],
    )
    assert _leaked(spans, 1.0, 1.2) < 1e-6


def test_discarded_take_does_not_come_back_by_padding() -> None:
    transcript = [
        _sentence(
            0,
            _word("isso", 0.0, 0.4),
            _word("e", 0.45, 0.7),
            _word("pronto", 0.75, 1.0),
        ),
        _sentence(1, _word("eu", 1.0, 1.2)),
        _sentence(2, _word("acho", 1.2, 1.6)),
    ]
    spans, _noise = transcript_spans(
        transcript,
        {1},
        sample_rate=RATE,
        duration_samples=4 * RATE,
        pad_before_ms=120,
        pad_after_ms=150,
    )
    assert _leaked(spans, 1.0, 1.2) < 1e-6


def test_dropped_filler_is_not_restored_by_padding() -> None:
    sentence = _sentence(
        0,
        _word("complete", 0.0, 0.2),
        _word("sentence", 0.2, 0.5),
        _word("hum", 1.0, 1.1),
    )
    spans, noise = transcript_spans(
        [sentence],
        set(),
        sample_rate=RATE,
        duration_samples=4 * RATE,
        pad_before_ms=120,
        pad_after_ms=150,
        internal_gap_mode="all",
        drop_isolated_words=True,
    )
    assert noise
    assert _leaked(spans, 1.0, 1.1) < 1e-6


def test_exclude_removed_audio_clips_a_late_padding_pass() -> None:
    from videoflow.application.timeline_builder import exclude_removed_audio

    transcript = [
        _sentence(
            0,
            _word("pronto", 0.75, 1.0),
            _word("eu", 1.0, 1.2),
            _word("acho", 1.25, 1.6),
        )
    ]
    spans = [(0, round(1.2 * RATE))]  # a later pass restored the cut
    result = exclude_removed_audio(
        spans,
        [(round(1.0 * RATE), round(1.2 * RATE))],
        transcript,
        set(),
        duration_samples=4 * RATE,
    )
    assert _leaked(result, 1.0, 1.2) < 1e-6


def test_exclude_removed_audio_is_a_noop_without_cuts() -> None:
    from videoflow.application.timeline_builder import exclude_removed_audio

    spans = [(0, 1000)]
    assert (
        exclude_removed_audio(
            spans,
            [],
            [_sentence(0, _word("a", 0.0, 0.01))],
            set(),
            duration_samples=4 * RATE,
        )
        == spans
    )


def test_word_next_to_a_cut_is_kept() -> None:
    sentence = _sentence(
        0,
        _word("isso", 0.0, 0.4),
        _word("e", 0.45, 0.7),
        _word("pronto", 0.75, 1.0),
        _word("eu", 1.0, 1.2),
        _word("acho", 1.25, 1.6),
    )
    spans, _noise = transcript_spans(
        [sentence],
        set(),
        sample_rate=RATE,
        duration_samples=4 * RATE,
        pad_before_ms=120,
        pad_after_ms=150,
        forced_cuts=[(round(1.0 * RATE), round(1.2 * RATE))],
    )
    assert _leaked(spans, 1.25, 1.6) > 0.0
