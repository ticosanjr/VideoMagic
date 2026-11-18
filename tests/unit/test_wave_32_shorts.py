from __future__ import annotations

from videoflow.application.shorts_tighten import tighten_clip
from videoflow.application.word_cuts import plan_word_cuts
from videoflow.domain.state import Sentence, WordTiming


def test_tighten_moves_cuts_out_of_words() -> None:
    words = [
        WordTiming(word="hello", start_sample=1000, end_sample=5000, probability=0.9),
        WordTiming(word="world", start_sample=6000, end_sample=9000, probability=0.9),
    ]
    result = tighten_clip(
        start_sample=2000,
        end_sample=8000,
        speech_intervals=[(2000, 8000)],
        words=words,
        sample_rate=48000,
        start_pad_ms=0,
        end_pad_ms=0,
    )
    assert result.start_sample == 1000
    assert result.end_sample == 9000


def test_pt_fillers_are_isolated_tokens() -> None:
    sentence = Sentence(
        id=0,
        start_sample=0,
        end_sample=8000,
        text="hum tipo resultado",
        words=[
            WordTiming(word="hum", start_sample=0, end_sample=1000, probability=0.9),
            WordTiming(word="tipo", start_sample=1000, end_sample=2000, probability=0.9),
            WordTiming(word="resultado", start_sample=2000, end_sample=3000, probability=0.9),
        ],
    )
    plan = plan_word_cuts([sentence], set(), sample_rate=48000, remove_fillers=True)
    assert plan.cut_words == 2
