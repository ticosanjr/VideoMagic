from __future__ import annotations

from pathlib import Path

from videoflow.application.timeline_snapshots import (
    delete_snapshot,
    list_snapshots,
    read_snapshot,
    save_snapshot,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    VideoSegment,
)
from videoflow.steps.base import StepIO
from videoflow.steps.timeline_load import TimelineLoadParams, TimelineLoadStep


def state(tmp_path: Path) -> ProjectState:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    return ProjectState(
        media_info=MediaInfo(
            source_path=str(source),
            duration_frames=50,
            fps_num=25,
            fps_den=1,
            width=640,
            height=360,
            audio_sample_rate=48000,
        ),
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_in_frame=0,
                source_out_frame=25,
                timeline_in_frame=0,
                timeline_out_frame=25,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            )
        ],
    )


def test_snapshot_round_trip(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    saved = save_snapshot(state(tmp_path), name="First cut", job_id="job-1")
    assert saved["name"] == "First cut"
    assert saved["duration_sec"] == 1.0
    assert Path(saved["path"]).is_file()
    assert [item["id"] for item in list_snapshots()] == [saved["id"]]

    metadata, loaded = read_snapshot(saved["id"])
    assert metadata["revision"] == 1
    assert loaded.video_segments[0].clip_id == "v1"
    assert delete_snapshot(saved["id"]) is True
    assert list_snapshots() == []


def test_timeline_load_step_reads_a_snapshot(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    saved = save_snapshot(state(tmp_path), name="Loaded cut")
    context = PipelineContext(
        source=tmp_path / "unused.mp4",
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
    )
    TimelineLoadStep().run(
        context,
        TimelineLoadParams(snapshot_id=saved["id"]),
        StepIO(),
    )
    assert context.state is not None
    assert context.state.video_segments[0].clip_id == "v1"
    assert context.media is not None
    assert context.media.source_path == str(tmp_path / "source.mp4")
    assert context.metadata["timeline_snapshot"]["name"] == "Loaded cut"
