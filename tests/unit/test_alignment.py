from __future__ import annotations

from videoflow.application.alignment import plausible_ms, refine_transcript
from videoflow.domain.state import Sentence, WordTiming


def _sentence(identifier: int, words: list[tuple[str, int, int]]) -> Sentence:
    return Sentence(
        id=identifier,
        start_sample=words[0][1],
        end_sample=words[-1][2],
        text=" ".join(word for word, _start, _end in words),
        words=[
            WordTiming(
                word=word,
                start_sample=start,
                end_sample=end,
                probability=0.9,
            )
            for word, start, end in words
        ],
    )


def test_implausibly_long_word_is_capped_to_a_plausible_span() -> None:
    sentence = _sentence(0, [("ataques", 1000, 3000)])
    refined, stats = refine_transcript(
        [sentence],
        [(900, 2800)],
        sample_rate=1000,
    )
    word = refined[0].words[0]
    assert 900 <= word.start_sample < word.end_sample <= 2800
    assert word.end_sample - word.start_sample <= 1140
    assert stats["implausible_before"] == 1


def test_overlapping_words_are_separated() -> None:
    sentence = _sentence(0, [("um", 1000, 2000), ("dois", 1500, 2500)])
    refined, _stats = refine_transcript(
        [sentence],
        [(900, 3000)],
        sample_rate=1000,
    )
    words = refined[0].words
    assert words[0].end_sample <= words[1].start_sample


def test_plausible_word_is_left_alone() -> None:
    sentence = _sentence(0, [("casa", 1000, 1300)])
    refined, stats = refine_transcript(
        [sentence],
        [(900, 1600)],
        sample_rate=1000,
    )
    assert refined[0].words[0].start_sample == 1000
    assert refined[0].words[0].end_sample == 1300
    assert stats["adjusted"] == 0


def test_plausible_ms_scales_with_word_length() -> None:
    assert plausible_ms("a") < plausible_ms("extraordinariamente")


def test_snap_moves_to_the_quietest_frame() -> None:
    from videoflow.application.alignment import _snap

    def rms(start: int, end: int) -> int:
        return 100 if 250 <= start <= 300 else 5000

    position = _snap(
        rms,
        500,
        direction=-1,
        limit=300,
        frame=100,
        sample_rate=1000,
    )
    assert position == 300


def test_plausible_ms_has_a_ceiling() -> None:
    assert plausible_ms("a" * 100) == 1500
