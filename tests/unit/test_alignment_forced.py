from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, Sentence, WordTiming
from videoflow.steps import alignment_forced as module
from videoflow.steps.alignment_forced import ForcedAlignmentParams, ForcedAlignmentStep
from videoflow.steps.base import StepIO


def test_forced_alignment_adds_word_timings(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"RIFF")
    context = PipelineContext(
        source=source,
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        pcm_path=source,
        media=MediaInfo(
            source_path=str(source),
            duration_frames=60,
            fps_num=30,
            fps_den=1,
            width=640,
            height=360,
            audio_sample_rate=48000,
        ),
        transcript=[Sentence(id=1, start_sample=0, end_sample=48000, text="Hello world.")],
    )

    class FakeWhisper:
        @staticmethod
        def available(size="small", **kwargs):
            return True

        def __init__(self, **kwargs):
            pass

        def transcribe(self, path, sample_rate):
            return [
                Sentence(
                    id=1,
                    start_sample=0,
                    end_sample=48000,
                    text="Hello world.",
                    words=[
                        WordTiming(
                            word="Hello",
                            start_sample=1000,
                            end_sample=9000,
                            probability=1.0,
                        ),
                        WordTiming(
                            word="world",
                            start_sample=9000,
                            end_sample=18000,
                            probability=1.0,
                        ),
                    ],
                )
            ]

    monkeypatch.setattr(module, "FasterWhisperAdapter", FakeWhisper)
    ForcedAlignmentStep().run(context, ForcedAlignmentParams(), StepIO())
    assert context.transcript[0].words[0].word == "Hello"
    assert context.transcript[0].start_sample == 1000
    assert context.transcript[0].end_sample == 18000
    assert context.metadata["forced_alignment"]["aligned"] == 1
    assert Path(context.artifacts["forced_alignment"]).is_file()


def test_forced_alignment_persists_detected_language(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"RIFF")
    context = PipelineContext(
        source=source,
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        pcm_path=source,
        media=MediaInfo(
            source_path=str(source),
            duration_frames=60,
            fps_num=30,
            fps_den=1,
            width=640,
            height=360,
            audio_sample_rate=48000,
        ),
        transcript=[Sentence(id=1, start_sample=0, end_sample=48000, text="Hello.")],
    )

    class FakeWhisper:
        last_language = "en"
        last_language_probability = 0.93

        @staticmethod
        def available(size="small", **kwargs):
            return True

        def __init__(self, **kwargs):
            pass

        def transcribe(self, path, sample_rate):
            self.last_language = "en"
            return [
                Sentence(
                    id=1,
                    start_sample=0,
                    end_sample=48000,
                    text="Hello.",
                    words=[
                        WordTiming(word="Hello", start_sample=0, end_sample=9000, probability=1.0)
                    ],
                )
            ]

    monkeypatch.setattr(module, "FasterWhisperAdapter", FakeWhisper)
    ForcedAlignmentStep().run(context, ForcedAlignmentParams(), StepIO())

    assert context.transcript_language == "en"
    assert context.language_confidence == pytest.approx(0.93)
    assert context.metadata["forced_alignment"]["language"] == "en"


def test_word_ranges_use_bisect_for_ordered_words() -> None:
    from videoflow.steps.alignment_forced import _word_ranges

    words = [("a", 0, 100), ("b", 100, 200), ("c", 200, 300)]
    sentences = [
        Sentence(id=1, start_sample=0, end_sample=100, text="a"),
        Sentence(id=2, start_sample=100, end_sample=300, text="b c"),
    ]

    assert _word_ranges(words, sentences) == [(0, 1), (1, 3)]


def test_word_ranges_fall_back_for_unordered_words() -> None:
    from videoflow.steps.alignment_forced import _word_ranges

    words = [("b", 100, 200), ("a", 0, 100)]
    sentences = [Sentence(id=1, start_sample=0, end_sample=300, text="a b")]

    assert _word_ranges(words, sentences) is None
