from __future__ import annotations

from videoflow.application.word_cuts import (
    WordCut,
    WordRef,
    _split_cut,
    plan_word_cuts,
)
from videoflow.domain.state import Sentence, WordTiming


def _sentence(
    identifier: int,
    texts: list[str],
    *,
    start: float = 0.0,
    step: float = 0.3,
    rate: int = 1000,
) -> Sentence:
    words: list[WordTiming] = []
    cursor = start
    for text in texts:
        words.append(
            WordTiming(
                word=text,
                start_sample=round(cursor * rate),
                end_sample=round((cursor + step * 0.8) * rate),
                probability=1.0,
            )
        )
        cursor += step
    return Sentence(
        id=identifier,
        start_sample=words[0].start_sample,
        end_sample=words[-1].end_sample,
        text=" ".join(texts),
        words=words,
    )


def _plan(sentences: list[Sentence], **kwargs: object):
    return plan_word_cuts(
        sentences,
        set(),
        sample_rate=1000,
        max_cut_ratio=1.0,
        max_gap_seconds=120.0,
        **kwargs,
    )


def test_stutter_keeps_the_last_occurrence() -> None:
    sentence = _sentence(0, ["fazia", "fazia", "fazia", "coisa"])
    plan = _plan([sentence])
    assert plan.cut_words == 2
    assert len(plan.cuts) == 1
    assert plan.report[0]["reason"] == "stutter"
    assert plan.report[0]["words"] == 2


def test_prefix_retake_cuts_the_earlier_sentence() -> None:
    sentences = [
        _sentence(0, ["ela", "pegou", "o", "modelo", "e", "construiu"]),
        _sentence(
            1,
            ["ela", "pegou", "o", "modelo", "e", "construiu", "e", "colocou"],
            start=1.8,
        ),
    ]
    plan = _plan(sentences)
    assert plan.cut_words == 6
    assert plan.report[0]["reason"] == "prefix_tail"
    assert plan.report[0]["start_sec"] == 0.0


def test_tail_retake_preserves_the_unique_prefix() -> None:
    sentences = [
        _sentence(0, ["prefixo", "unico", "e", "colocou", "lado", "a", "lado"]),
        _sentence(
            1,
            ["e", "colocou", "lado", "a", "lado", "com", "sistemas"],
            start=2.1,
        ),
    ]
    plan = _plan(sentences)
    assert plan.cut_words == 5
    assert plan.report[0]["reason"] == "prefix_tail"
    assert plan.report[0]["text"].startswith("e colocou")
    assert plan.report[0]["start_sec"] == 0.6


def test_local_ngram_repeat_cuts_only_the_earlier_occurrence() -> None:
    sentence = _sentence(
        0,
        ["alpha", "beta", "gamma", "delta", "alpha", "beta", "gamma", "delta"],
    )
    plan = _plan([sentence])
    assert plan.cut_words == 4
    assert plan.report[0]["reason"] == "ngram"
    assert plan.report[0]["start_sec"] == 0.0


def test_unique_words_are_not_cut() -> None:
    words = [
        WordRef(0, 0, 0, 200, "alpha", "alpha", False),
        WordRef(1, 0, 300, 500, "alpha", "alpha", False),
        WordRef(2, 0, 600, 800, "unico", "unico", False),
    ]
    from collections import Counter

    runs = _split_cut(
        WordCut(0, 2, "ngram", "alpha alpha unico"),
        words,
        Counter({"alpha": 2, "unico": 1}),
    )
    assert [(run.start, run.end) for run in runs] == [(0, 1)]


def test_max_cut_ratio_limits_the_plan() -> None:
    texts = ["alpha", "beta", "gamma", "delta"] * 4
    sentence = _sentence(0, texts)
    plan = plan_word_cuts(
        [sentence],
        set(),
        sample_rate=1000,
        max_cut_ratio=0.1,
        max_gap_seconds=120.0,
    )
    assert plan.cut_words <= 1


def test_empty_transcript_returns_no_cuts() -> None:
    plan = _plan([])
    assert plan.cuts == []
    assert plan.cut_words == 0
    assert plan.total_words == 0


def test_plan_to_dict_reports_ratio() -> None:
    plan = _plan([_sentence(0, ["fazia", "fazia", "coisa"])])
    payload = plan.to_dict()
    assert payload["cut_words"] == 1
    assert payload["total_words"] == 3
    assert payload["ratio"] == 0.333333


def test_punctuation_only_words_and_single_word_sentences_are_ignored() -> None:
    sentences = [
        _sentence(0, ["alpha", "...", "beta"]),
        _sentence(1, ["unico"], start=1.0),
    ]
    plan = _plan(sentences)
    assert plan.total_words == 3
    assert plan.cuts == []


def test_stopword_only_repeats_are_not_cut() -> None:
    sentences = [
        _sentence(0, ["de", "que", "a", "de", "que", "a"]),
        _sentence(1, ["de", "que", "a", "outra", "coisa"], start=2.0),
    ]
    plan = _plan(sentences)
    assert plan.cuts == []


def test_ngram_beyond_the_window_is_not_cut() -> None:
    tokens = ["alpha", "beta", "gamma", "delta", "alpha", "beta", "gamma", "delta"]
    timings = []
    for index, token in enumerate(tokens):
        start = index * 300 if index < 4 else 500_000 + (index - 4) * 300
        timings.append(
            WordTiming(
                word=token,
                start_sample=start,
                end_sample=start + 200,
                probability=1.0,
            )
        )
    sentence = Sentence(
        id=0,
        start_sample=0,
        end_sample=500_900,
        text=" ".join(tokens),
        words=timings,
    )
    plan = plan_word_cuts(
        [sentence],
        set(),
        sample_rate=1000,
        max_cut_ratio=1.0,
        max_gap_seconds=10.0,
    )
    assert plan.cuts == []


def test_max_cuts_limits_selected_ranges() -> None:
    sentences = [
        _sentence(0, ["um", "um", "dois", "dois", "tres", "tres"]),
    ]
    plan = plan_word_cuts(
        sentences,
        set(),
        sample_rate=1000,
        max_cut_ratio=1.0,
        max_gap_seconds=120.0,
        max_cuts=1,
    )
    assert len(plan.report) == 1
