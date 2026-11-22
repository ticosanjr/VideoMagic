from __future__ import annotations

import pytest

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


def test_rms_reader_handles_audio_layouts(tmp_path) -> None:
    import array
    import wave

    from videoflow.application import alignment

    stereo = tmp_path / "stereo.wav"
    with wave.open(str(stereo), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(1000)
        samples = array.array("h", [100, 100, 200, 200, 0, 0])
        handle.writeframes(samples.tobytes())
    rms = alignment._Rms(stereo, 48000)
    assert rms.rate == 1000
    assert rms(0, 3) > 0
    assert rms(10, 11) == 0
    rms.close()
    assert rms(0, 1) == 0

    eight_bit = tmp_path / "eight.wav"
    with wave.open(str(eight_bit), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(1)
        handle.setframerate(1000)
        handle.writeframes(b"\x80\x80")
    wide = alignment._Rms(eight_bit, 1000)
    with pytest.raises(ValueError, match="Unsupported PCM sample width: 1"):
        wide(0, 2)
    wide.close()

    assert alignment._Rms(tmp_path / "missing.wav", 1000)(0, 1) == 0

    class Broken:
        def setpos(self, position):
            raise OSError("bad seek")

    reader = alignment._Rms(stereo, 1000)
    reader.handle = Broken()
    reader.width = 2
    assert reader(0, 1) == 0


def test_snap_and_vad_edges() -> None:
    from videoflow.application import alignment

    assert alignment._snap(None, 10, direction=1, limit=10, frame=1, sample_rate=1) == 10
    assert alignment._snap(lambda a, b: 0, 0, direction=-1, limit=0, frame=10, sample_rate=1) == 0
    assert alignment._vad_span(0, 100, [(200, 300)]) is None
    assert alignment._vad_span(0, 100, [(0, 50)]) == (0, 50)
    assert alignment.refine_transcript([], []) == ([], {"words": 0, "adjusted": 0})


def test_refine_shifts_overlapping_sentences_and_fills_gaps() -> None:
    first = _sentence(0, [("one", 0, 1000)])
    second = Sentence(
        id=1,
        start_sample=500,
        end_sample=1500,
        text="two",
        words=[
            WordTiming(
                word="two",
                start_sample=500,
                end_sample=1500,
                probability=0.8,
            )
        ],
    )
    refined, stats = refine_transcript(
        [first, second], [(0, 2000)], sample_rate=1000
    )
    assert refined[1].words[0].start_sample >= refined[0].words[0].end_sample
    assert stats["adjusted"] >= 1

    tiny = _sentence(2, [("go", 0, 10)])
    merged, stats = refine_transcript(
        [tiny], [(0, 100)], sample_rate=1000, min_word_ms=40
    )
    assert merged[0].words[0].end_sample - merged[0].words[0].start_sample >= 40
