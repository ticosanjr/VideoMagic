from __future__ import annotations

from videoflow.application.repeats import detect_repeated_cuts
from videoflow.domain.state import Sentence, WordTiming


def _sentence(identifier: int, texts: list[str], start: int) -> Sentence:
    words = []
    cursor = start
    for text in texts:
        words.append(
            WordTiming(
                word=text,
                start_sample=cursor,
                end_sample=cursor + 4_000,
                probability=0.9,
            )
        )
        cursor += 4_000
    return Sentence(
        id=identifier,
        start_sample=start,
        end_sample=cursor,
        text=" ".join(texts),
        words=words,
    )


def test_repeated_passage_keeps_the_last_occurrence() -> None:
    transcript = [
        _sentence(0, ["alpha", "beta", "gamma", "delta", "epsilon."], 0),
        _sentence(1, ["unique", "content", "here."], 40_000),
        _sentence(2, ["alpha", "beta", "gamma", "delta", "epsilon."], 60_000),
    ]
    cuts, report = detect_repeated_cuts(
        transcript,
        set(),
        sample_rate=48_000,
        min_words=5,
        max_gap_seconds=180,
        pad_ms=0,
    )
    assert cuts == [(0, 20_000)]
    assert report[0]["text"].startswith("alpha beta gamma")


def test_far_apart_repeat_is_treated_as_a_callback() -> None:
    transcript = [
        _sentence(0, ["alpha", "beta", "gamma", "delta", "epsilon."], 0),
        _sentence(1, ["alpha", "beta", "gamma", "delta", "epsilon."], 300 * 48_000),
    ]
    cuts, _report = detect_repeated_cuts(
        transcript,
        set(),
        sample_rate=48_000,
        min_words=5,
        max_gap_seconds=180,
    )
    assert cuts == []


def test_repeated_cuts_respect_the_maximum() -> None:
    transcript = [
        _sentence(0, ["alpha", "beta", "gamma", "delta", "epsilon."], 0),
        _sentence(1, ["alpha", "beta", "gamma", "delta", "epsilon."], 40_000),
        _sentence(2, ["alpha", "beta", "gamma", "delta", "epsilon."], 80_000),
    ]
    cuts, report = detect_repeated_cuts(
        transcript,
        set(),
        sample_rate=48_000,
        min_words=5,
        max_gap_seconds=180,
        max_cuts=1,
    )
    assert len(cuts) == 1
    assert len(report) == 1
