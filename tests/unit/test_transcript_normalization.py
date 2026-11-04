from __future__ import annotations

from videoflow.application.transcript import normalize_transcript
from videoflow.domain.state import Sentence, WordTiming


def word(text: str, start: int, end: int) -> WordTiming:
    return WordTiming(word=text, start_sample=start, end_sample=end, probability=0.9)


def sentence(identifier: int, text: str, start: int, end: int, words: list[WordTiming]) -> Sentence:
    return Sentence(
        id=identifier,
        start_sample=start,
        end_sample=end,
        text=text,
        words=words,
    )


def test_overlapping_segments_are_deduplicated() -> None:
    segments = [
        sentence(
            0,
            "Hello world",
            0,
            20_000,
            [word("Hello", 0, 10_000), word("world", 10_000, 20_000)],
        ),
        sentence(
            1,
            "world. Again",
            20_000,
            40_000,
            [word("world.", 20_000, 30_000), word("Again", 30_000, 40_000)],
        ),
    ]
    normalized = normalize_transcript(segments)
    assert [item.text for item in normalized] == ["Hello world.", "Again"]
    assert [item.id for item in normalized] == [0, 1]


def test_long_pause_splits_into_sentences() -> None:
    segments = [
        sentence(
            0,
            "one two three four five six",
            0,
            100_000,
            [
                word("one", 0, 10_000),
                word("two", 10_000, 20_000),
                word("three", 20_000, 30_000),
                word("four", 30_000, 40_000),
                word("Five", 150_000, 160_000),
                word("six.", 160_000, 170_000),
            ],
        )
    ]
    normalized = normalize_transcript(segments)
    assert [item.text for item in normalized] == ["one two three four", "Five six."]


def test_punctuation_tokens_are_joined_without_spaces() -> None:
    segments = [
        sentence(
            0,
            "version 3.1 arrived.",
            0,
            40_000,
            [
                word("version", 0, 10_000),
                word("3", 10_000, 20_000),
                word(".1", 20_000, 30_000),
                word("arrived.", 30_000, 40_000),
            ],
        )
    ]
    normalized = normalize_transcript(segments)
    assert normalized[0].text == "version 3.1 arrived."


def test_empty_transcript_stays_empty() -> None:
    assert normalize_transcript([]) == []


def test_repeated_srt_sentences_with_a_pause_are_preserved() -> None:
    segments = [
        sentence(0, "Same line.", 0, 48_000, []),
        sentence(1, "Same line.", 96_000, 144_000, []),
    ]
    normalized = normalize_transcript(segments)
    assert [item.text for item in normalized] == ["Same line.", "Same line."]
    assert [item.start_sample for item in normalized] == [0, 96_000]


def test_sentence_without_word_timings_uses_proportional_pseudo_words() -> None:
    segments = [sentence(0, "one two three four", 0, 40_000, [])]
    normalized = normalize_transcript(segments)
    assert normalized[0].text == "one two three four"
    assert [word.start_sample for word in normalized[0].words] == [
        0,
        10_000,
        20_000,
        30_000,
    ]


def test_empty_sentence_text_is_skipped() -> None:
    segments = [sentence(0, "", 0, 10_000, [])]
    assert normalize_transcript(segments) == []


def test_overlap_prefers_the_later_occurrence_and_its_timings() -> None:
    segments = [
        sentence(
            0,
            "alpha beta gamma.",
            0,
            30_000,
            [
                word("alpha", 0, 10_000),
                word("beta", 10_000, 20_000),
                word("gamma.", 20_000, 30_000),
            ],
        ),
        sentence(
            1,
            "beta gamma. delta.",
            20_000,
            50_000,
            [
                word("beta", 20_000, 30_000),
                word("gamma.", 30_000, 40_000),
                word("delta.", 40_000, 50_000),
            ],
        ),
    ]
    normalized = normalize_transcript(segments)
    assert [item.text for item in normalized] == ["alpha beta gamma.", "delta."]
    beta = next(
        word for item in normalized for word in item.words if word.word == "beta"
    )
    assert beta.start_sample == 20_000


def test_overlap_records_a_cut_for_the_earlier_occurrence() -> None:
    segments = [
        sentence(
            0,
            "alpha beta gamma.",
            0,
            30_000,
            [
                word("alpha", 0, 10_000),
                word("beta", 10_000, 20_000),
                word("gamma.", 20_000, 30_000),
            ],
        ),
        sentence(
            1,
            "beta gamma. delta.",
            20_000,
            50_000,
            [
                word("beta", 20_000, 30_000),
                word("gamma.", 30_000, 40_000),
                word("delta.", 40_000, 50_000),
            ],
        ),
    ]
    cuts: list[tuple[int, int]] = []
    normalize_transcript(segments, cuts=cuts)
    assert cuts == [(10_000, 20_000)]
