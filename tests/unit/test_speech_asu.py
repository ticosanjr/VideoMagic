from __future__ import annotations

import json
from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, Sentence, WordTiming
from videoflow.steps.base import StepIO
from videoflow.steps.speech_asu import SpeechAsuParams, SpeechAsuStep


def _word(text: str, start: int, end: int, probability: float = 0.9) -> WordTiming:
    return WordTiming(
        word=text,
        start_sample=start,
        end_sample=end,
        probability=probability,
    )


def _context(tmp_path: Path) -> PipelineContext:
    return PipelineContext(
        source=tmp_path / "source.wav",
        output=tmp_path / "out",
        work=tmp_path / "out" / "work",
        exports=tmp_path / "out" / "exports",
        media=MediaInfo(
            source_path=str(tmp_path / "source.wav"),
            duration_frames=100,
            fps_num=25,
            fps_den=1,
            width=320,
            height=240,
            audio_sample_rate=16_000,
        ),
        transcript=[
            Sentence(
                id=1,
                start_sample=0,
                end_sample=1600,
                text="Olá mundo.",
                words=[_word("Olá", 0, 800), _word("mundo.", 800, 1600)],
            ),
            Sentence(
                id=2,
                start_sample=4000,
                end_sample=5600,
                text="Segunda frase.",
                words=[_word("Segunda", 4000, 4800), _word("frase.", 4800, 5600)],
            ),
        ],
        metadata={
            "audio_events": [
                {
                    "label": "Cough",
                    "start_sample": 3900,
                    "end_sample": 4050,
                    "score": 0.8,
                    "action": "remove",
                }
            ]
        },
    )


def test_asu_groups_by_pause_and_punctuation(tmp_path: Path) -> None:
    context = _context(tmp_path)
    SpeechAsuStep().run(context, SpeechAsuParams(), StepIO())
    assert context.metadata["asu_report"]["count"] == 2
    asus = context.metadata["asus"]
    assert [item["asu_id"] for item in asus] == ["ASU_0001", "ASU_0002"]
    assert asus[0]["text"] == "Olá mundo."
    assert asus[1]["pause_before"] == 0.15
    assert asus[1]["noise_events"][0]["label"] == "Cough"
    assert asus[0]["words"][1]["idx"] == 1
    assert Path(context.artifacts["asus"]).is_file()
    payload = json.loads(Path(context.artifacts["asus"]).read_text(encoding="utf-8"))
    assert payload["sample_rate"] == 16_000


def test_asu_flags_adjacent_stutter(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.transcript[0].words = [
        _word("eu", 0, 400, 0.9),
        _word("eu", 450, 800, 0.9),
        _word("mundo.", 800, 1600, 0.9),
    ]
    SpeechAsuStep().run(context, SpeechAsuParams(), StepIO())
    assert context.metadata["asus"][0]["has_stutter_candidate"] is True


def test_asu_breaks_at_max_duration(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.transcript[0].words = [
        _word("a", index * 1000, index * 1000 + 900)
        for index in range(20)
    ]
    context.transcript[0].start_sample = 0
    context.transcript[0].end_sample = 20_000
    context.transcript[0].text = "a " * 20
    context.transcript = [context.transcript[0]]
    SpeechAsuStep().run(context, SpeechAsuParams(max_asu_sec=1.0), StepIO())
    assert context.metadata["asu_report"]["count"] >= 2
