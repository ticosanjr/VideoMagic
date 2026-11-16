"""NLE marker roundtrip for transcript, B-roll, and ducking changes."""

from __future__ import annotations

from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.domain.state import (
    MediaInfo,
    ProjectState,
    Sentence,
    WordTiming,
)
from videoflow.steps import nle_sync
from videoflow.steps.base import StepIO

RATE = 48000


def make_context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    (output / "work").mkdir(parents=True, exist_ok=True)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    sentence = Sentence(
        id=0,
        start_sample=0,
        end_sample=RATE,
        text="hello",
        words=[WordTiming(word="hello", start_sample=0, end_sample=RATE, probability=1.0)],
    )
    return PipelineContext(
        source=source,
        output=output,
        work=output / "work",
        exports=output / "exports",
        media=MediaInfo(
            source_path=str(source),
            duration_frames=300,
            fps_num=30,
            fps_den=1,
            width=1920,
            height=1080,
            audio_sample_rate=RATE,
        ),
        state=ProjectState(transcript=[sentence]),
        transcript=[sentence],
        shorts=[{"title": "Short"}],
    )


def test_timecode_and_marker_parsing() -> None:
    assert nle_sync._timecode_seconds("00:00:12.500") == 12.5
    assert nle_sync._timecode_seconds("bad:value") == 0.0
    assert nle_sync._timecode_seconds("3.5") == 3.5
    assert nle_sync._marker_params("", "plain note") is None
    assert nle_sync._marker_params("", "vf:duck level=-14 start=1 end=2") == (
        "ducking",
        {"level": "-14", "start": "1", "end": "2"},
    )
    assert nle_sync._marker_params("", "vf b-roll path=/tmp/a.mp4") == (
        "broll",
        {"path": "/tmp/a.mp4"},
    )


def test_fcpxml_markers_apply_transcript_broll_and_ducking(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    context = make_context(tmp_path)
    broll = tmp_path / "broll.mp4"
    broll.write_bytes(b"x")
    path = context.output / "timeline.fcpxml"
    path.write_text(
        "<fcpxml>"
        "<marker start='0s' duration='1s' value='vf transcript shift=0.5'/>"
        f"<marker start='2s' duration='3s' value='vf broll path={broll} duration=2.5'/>"
        "<marker start='1s' duration='2s' value='vf ducking level=-18'/>"
        "<marker value='plain editorial note'/>"
        "</fcpxml>",
        encoding="utf-8",
    )

    nle_sync.NleSyncStep().run(
        context,
        nle_sync.NleSyncParams(format="fcpxml", path=str(path), apply=True),
        StepIO(),
    )

    report = context.metadata["sync_back_report"]
    assert report["applied"] is True
    assert report["transcript_updates"] == 1
    assert report["broll_updates"] == 1
    assert report["ducking_updates"] == 1
    assert context.transcript[0].start_sample == RATE // 2
    assert context.state.transcript[0].words[0].end_sample == RATE + RATE // 2
    assert context.metadata["broll_plan"]["Short"][0]["path"] == str(broll)
    assert context.metadata["broll_plan"]["Short"][0]["duration_sec"] == 2.5
    assert context.metadata["nle_ducking"][0]["level_db"] == -18
    ducking = context.output / "audio" / "ducking.json"
    assert ducking.is_file()


def test_mlt_markers_and_invalid_marker_values(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    context = make_context(tmp_path)
    path = context.output / "timeline.kdenlive"
    path.write_text(
        "<mlt><producer/>"
        "<marker in='00:00:00.000' out='00:00:01.000' text='vf:transcript offset=bad'/>"
        "<marker in='00:00:01.000' out='00:00:02.000' text='vf:broll duration=2'/>"
        "<marker in='00:00:01.000' out='00:00:02.000' text='vf:duck level=bad'/>"
        "</mlt>",
        encoding="utf-8",
    )

    nle_sync.NleSyncStep().run(
        context,
        nle_sync.NleSyncParams(format="mlt", path=str(path), apply=True),
        StepIO(),
    )

    report = context.metadata["sync_back_report"]
    assert report["transcript_updates"] == 0
    assert report["broll_updates"] == 0
    assert report["ducking_updates"] == 0
    assert report["applied"] is False
    assert len(report["warnings"]) == 3
