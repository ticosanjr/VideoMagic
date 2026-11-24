"""Aggressive but safe decupage profiles and unified audio targets."""

from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application.editorial_clean import clean_editorial
from videoflow.application.qa_final import _dead_air_limit_ms
from videoflow.application.silence import (
    PACING_PROFILES,
    resolve_pacing_profile,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, PipelineState, ProjectState, Sentence
from videoflow.steps.audio_finalize import AudioFinalizeParams, AudioFinalizeStep
from videoflow.steps.base import StepIO

RATE = 48_000


def _sentence(identifier: int, text: str, start_ms: int, end_ms: int) -> Sentence:
    return Sentence(
        id=identifier,
        text=text,
        start_sample=round(start_ms * RATE / 1000),
        end_sample=round(end_ms * RATE / 1000),
        words=[],
    )


def test_pacing_profiles_are_explicit_and_overridable() -> None:
    assert PACING_PROFILES["tight"]["qa_dead_air_ms"] == 550
    assert PACING_PROFILES["balanced"]["max_pause_ms"] == 420
    assert PACING_PROFILES["relaxed"]["pad_after_ms"] == 170
    resolved = resolve_pacing_profile(
        "balanced",
        max_pause_ms=300,
        pad_before_ms=70,
        pad_after_ms=100,
    )
    assert resolved["max_pause_ms"] == 300
    assert resolved["pad_before_ms"] == 70
    assert resolved["pad_after_ms"] == 100
    assert resolved["qa_dead_air_ms"] >= 550


def test_paraphrase_is_discarded_without_an_external_llm() -> None:
    first = _sentence(
        0,
        "Hoje eu vou te mostrar como usar X",
        0,
        4000,
    )
    second = _sentence(
        1,
        "Nesse vídeo eu vou explicar como usar X na prática.",
        5000,
        9500,
    )
    result = clean_editorial([first, second], semantic=False)
    assert result.discarded_sentence_ids == (0,)
    assert [item.id for item in result.transcript] == [1]


def test_second_pass_catches_residual_repetition_after_first_clean() -> None:
    first = _sentence(0, "primeiro eu vou mostrar o produto", 0, 2000)
    second = _sentence(1, "agora eu vou mostrar o produto completo", 3000, 5000)
    third = _sentence(2, "agora eu vou mostrar o produto completo mesmo.", 6000, 8500)
    result = clean_editorial(
        [first, second, third],
        semantic=False,
        second_pass=True,
        max_discard_ratio=0.75,
    )
    assert set(result.discarded_sentence_ids) == {0, 1}
    assert [item.id for item in result.transcript] == [2]


def test_audio_finalize_explicit_target_lufs_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    output = tmp_path / "out"
    output.mkdir()
    context = PipelineContext(
        source=source,
        output=output,
        work=output / "work",
        exports=output / "exports",
        media=MediaInfo(
            source_path=str(source),
            duration_frames=60,
            fps_num=30,
            fps_den=1,
            width=320,
            height=240,
            audio_sample_rate=RATE,
        ),
        metadata={},
    )
    captured: dict[str, object] = {}

    class Result:
        path = str(output / "audio" / "final.wav")
        integrated_lufs = -14.0
        warnings: list[str] = []

        def to_dict(self):
            return {"integrated_lufs": -14.0, "warnings": []}

    def fake_finalize(voice, target, **kwargs):
        captured["target"] = kwargs.get("target_lufs")
        return Result()

    # The step imports finalize_audio directly.
    monkeypatch.setattr("videoflow.steps.audio_finalize.finalize_audio", fake_finalize)
    Path(Result.path).parent.mkdir(parents=True, exist_ok=True)
    Path(Result.path).write_bytes(b"wav")
    AudioFinalizeStep().run(
        context,
        AudioFinalizeParams(target_lufs=-14.0),
        StepIO(stage="audio.finalize"),
    )
    assert captured["target"] == -14.0


def test_qa_dead_air_reads_the_pacing_profile() -> None:
    state = ProjectState(
        pipeline=PipelineState(metadata={"qa_dead_air_ms": 550}),
    )
    assert _dead_air_limit_ms(state) == 550
    assert _dead_air_limit_ms(ProjectState()) == 550


def test_export_defaults_share_the_mix_audio_source() -> None:
    from videoflow.application.delivery_bundle import DeliveryBundleRequest
    from videoflow.steps.video_export import VideoExportParams

    assert VideoExportParams().audio_source == "mix"
    assert DeliveryBundleRequest().audio_source == "mix"
