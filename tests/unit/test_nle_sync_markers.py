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


def test_xmeml_clip_ranges_and_markers_roundtrip(tmp_path: Path, monkeypatch) -> None:
    from videoflow.domain.state import AudioSegment, VideoSegment

    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    context = make_context(tmp_path)
    context.state = ProjectState(
        transcript=context.transcript,
        video_segments=[
            VideoSegment(
                clip_id="c1",
                source_in_frame=0,
                source_out_frame=30,
                timeline_in_frame=0,
                timeline_out_frame=30,
            ),
            VideoSegment(
                clip_id="c2",
                source_in_frame=0,
                source_out_frame=30,
                timeline_in_frame=30,
                timeline_out_frame=60,
            ),
        ],
        audio_segments=[
            AudioSegment(
                clip_id="c1",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            ),
            AudioSegment(
                clip_id="c2",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=48000,
                timeline_out_sample=96000,
            ),
        ],
    )
    path = context.output / "timeline.xml"
    path.write_text(
        "<xmeml><sequence><media><video><track>"
        "<clipitem><start>0</start><end>30</end></clipitem>"
        "<clipitem><start>42</start><end>72</end></clipitem>"
        "</track></video></media>"
        "<marker><name>vf:transcript shift=0.5</name><in>0</in><out>30</out></marker>"
        "<marker><name>vf:ducking level=-20</name><in>30</in><out>60</out></marker>"
        "</sequence></xmeml>",
        encoding="utf-8",
    )

    assert nle_sync._clip_ranges(path, "xmeml", 30.0) == [(0.0, 1.0), (1.4, 1.0)]
    markers = nle_sync._markers(path, "xmeml", 30.0)
    assert markers[0][0] == "transcript"
    assert markers[0][1] == 0.0
    assert markers[1][0] == "ducking"
    assert markers[1][1] == 1.0

    nle_sync.NleSyncStep().run(
        context,
        nle_sync.NleSyncParams(format="xmeml", path=str(path), apply=True),
        StepIO(),
    )

    report = context.metadata["sync_back_report"]
    assert report["format"] == "xmeml"
    assert report["applied"] is True
    assert context.state.video_segments[1].timeline_in_frame == 42
    assert context.transcript[0].start_sample == RATE // 2


def test_nle_sync_parser_edge_cases(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    context = make_context(tmp_path)
    assert nle_sync._seconds("bad") == 0.0
    assert nle_sync._seconds("1/0") > 0.0
    assert nle_sync._timecode_seconds("") == 0.0
    assert nle_sync._timecode_seconds("a:b") == 0.0

    malformed = tmp_path / "timeline.xml"
    malformed.write_text(
        "<xmeml><sequence><media><video><track>"
        "<clipitem><start>x</start><end>y</end></clipitem>"
        "</track></video></media></sequence></xmeml>",
        encoding="utf-8",
    )
    assert nle_sync._clip_ranges(malformed, "xmeml", 30.0) == []
    assert nle_sync._markers(malformed, "xmeml", 30.0) == []

    nle_sync.NleSyncStep().run(
        context,
        nle_sync.NleSyncParams(format="xmeml", path=""),
        StepIO(),
    )
    assert context.metadata["sync_back_report"]["warnings"]
