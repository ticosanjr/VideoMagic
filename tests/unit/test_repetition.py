from __future__ import annotations

from videoflow.application.repetition import detect_repetitions
from videoflow.application.word_cuts import plan_word_cuts
from videoflow.domain.state import Sentence, WordTiming


def _sentence(
    identifier: int,
    tokens: list[tuple[str, float, float]],
    *,
    low_confidence: set[str] | None = None,
) -> Sentence:
    flagged = low_confidence or set()
    words = [
        WordTiming(
            word=text,
            start_sample=round(start * 1000),
            end_sample=round(end * 1000),
            probability=1.0,
            low_confidence=text in flagged,
        )
        for text, start, end in tokens
    ]
    return Sentence(
        id=identifier,
        start_sample=words[0].start_sample,
        end_sample=words[-1].end_sample,
        text=" ".join(word.word for word in words),
        words=words,
    )


def test_immediate_short_word_is_detected() -> None:
    sentence = _sentence(
        0,
        [("eu", 0.0, 0.2), ("eu", 0.25, 0.45), ("acho", 0.5, 0.9)],
    )
    plan = detect_repetitions([sentence], set(), sample_rate=1000)
    assert len(plan.cuts) == 1
    assert plan.cuts[0].reason == "stutter"


def test_cross_sentence_repeat_is_detected() -> None:
    sentences = [
        _sentence(0, [("vamos", 0.0, 0.3), ("projeto", 0.6, 0.95)]),
        _sentence(1, [("projeto", 1.3, 1.65), ("funciona", 1.7, 2.1)]),
    ]
    plan = detect_repetitions(sentences, set(), sample_rate=1000)
    assert len(plan.cuts) == 1
    assert plan.cuts[0].text == "projeto projeto"


def test_stopword_phrase_repeat_is_detected() -> None:
    sentence = _sentence(
        0,
        [
            ("de", 0.0, 0.1),
            ("que", 0.1, 0.2),
            ("a", 0.2, 0.3),
            ("de", 0.35, 0.45),
            ("que", 0.45, 0.55),
            ("a", 0.55, 0.65),
        ],
    )
    plan = detect_repetitions([sentence], set(), sample_rate=1000)
    assert len(plan.cuts) == 1
    assert plan.cuts[0].reason == "phrase"


def test_punctuated_emphasis_is_ambiguous() -> None:
    sentence = _sentence(
        0,
        [("não,", 0.0, 0.2), ("não", 0.25, 0.45), ("vou", 0.5, 0.9)],
    )
    plan = detect_repetitions([sentence], set(), sample_rate=1000)
    assert plan.cuts == []
    assert len(plan.ambiguous) == 1


def test_emphasis_with_a_longer_pause_is_ambiguous() -> None:
    sentence = _sentence(
        0,
        [("não", 0.0, 0.2), ("não", 0.7, 0.9), ("vou", 0.95, 1.2)],
    )
    plan = detect_repetitions([sentence], set(), sample_rate=1000)
    assert plan.cuts == []
    assert len(plan.ambiguous) == 1


def test_numbers_are_ambiguous() -> None:
    sentence = _sentence(
        0,
        [("2024", 0.0, 0.2), ("2024", 0.25, 0.45), ("foi", 0.5, 0.9)],
    )
    plan = detect_repetitions([sentence], set(), sample_rate=1000)
    assert plan.cuts == []
    assert len(plan.ambiguous) == 1


def test_low_confidence_repeat_is_ambiguous() -> None:
    sentence = _sentence(
        0,
        [("casa", 0.0, 0.2), ("casa", 0.25, 0.45), ("nova", 0.5, 0.9)],
        low_confidence={"casa"},
    )
    plan = detect_repetitions([sentence], set(), sample_rate=1000)
    assert plan.cuts == []
    assert len(plan.ambiguous) == 1


def test_gap_beyond_the_window_is_not_a_repeat() -> None:
    sentence = _sentence(
        0,
        [("casa", 0.0, 0.2), ("casa", 3.0, 3.2), ("nova", 3.25, 3.6)],
    )
    plan = detect_repetitions([sentence], set(), sample_rate=1000)
    assert plan.cuts == []
    assert plan.ambiguous == []


def test_there_is_no_cut_count_limit() -> None:
    tokens: list[tuple[str, float, float]] = []
    cursor = 0.0
    for _ in range(60):
        tokens.extend(
            [
                ("casa", cursor, cursor + 0.1),
                ("casa", cursor + 0.12, cursor + 0.22),
                ("nova", cursor + 0.24, cursor + 0.36),
            ]
        )
        cursor += 0.5
    plan = plan_word_cuts([_sentence(0, tokens)], set(), sample_rate=1000)
    assert plan.cut_words == 60
    assert len(plan.report) == 60


def test_plan_word_cuts_removes_short_and_cross_sentence_repeats() -> None:
    sentences = [
        _sentence(0, [("eu", 0.0, 0.2), ("eu", 0.25, 0.45), ("projeto", 0.6, 0.95)]),
        _sentence(1, [("projeto", 1.3, 1.65), ("funciona", 1.7, 2.1)]),
    ]
    plan = plan_word_cuts(sentences, set(), sample_rate=1000)
    text = [item["text"] for item in plan.report]
    assert "eu" in text
    assert "projeto" in text
    assert plan.cut_words == 2
