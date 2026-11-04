"""Edge branches shared by the exporters."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from videoflow.domain.errors import ExportError
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.exporters import common


def state(tmp_path: Path) -> ProjectState:
    source = tmp_path / "source.mp4"
    if not source.exists():
        source.write_bytes(b"x")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=120,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )
    return ProjectState(
        media_info=media,
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_in_frame=0,
                source_out_frame=30,
                timeline_in_frame=0,
                timeline_out_frame=30,
            ),
            VideoSegment(
                clip_id="v2",
                source_in_frame=30,
                source_out_frame=60,
                timeline_in_frame=30,
                timeline_out_frame=60,
            ),
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            ),
            AudioSegment(
                clip_id="v2",
                source_in_sample=48000,
                source_out_sample=96000,
                timeline_in_sample=48000,
                timeline_out_sample=96000,
            ),
        ],
    )


def test_require_timeline_rejects_clips_past_the_media(tmp_path: Path) -> None:
    payload = state(tmp_path)
    payload.video_segments[0].source_out_frame = 999
    with pytest.raises(ExportError, match="exceeds the media duration"):
        common.require_timeline(payload)

    payload = state(tmp_path)
    payload.audio_segments[0].source_out_sample = 10**9
    with pytest.raises(ExportError, match="exceeds the media duration"):
        common.require_timeline(payload)

    payload = state(tmp_path)
    payload.audio_segments[0].timeline_in_sample = 4800
    with pytest.raises(ExportError, match="not packed"):
        common.require_timeline(payload)

    payload = state(tmp_path)
    payload.audio_segments[1].clip_id = "v1"
    with pytest.raises(ExportError, match="Duplicate audio clip id"):
        common.require_timeline(payload)


def test_require_timeline_returns_timebase_and_ids(tmp_path: Path) -> None:
    media, video, audio = common.require_timeline(state(tmp_path))
    assert set(video) == {"v1", "v2"}
    assert set(audio) == {"v1", "v2"}
    assert common.rate_parts(media).fps_num == 30


def test_write_text_removes_the_temporary_file_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "out" / "file.txt"

    def fail(source: str, destination: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        common.write_text(target, "data")
    assert list((tmp_path / "out").glob("*.tmp")) == []


def test_require_timeline_reports_the_first_video_gap(tmp_path: Path) -> None:
    payload = state(tmp_path)
    payload.video_segments[0].timeline_in_frame = 5
    payload.video_segments[0].timeline_out_frame = 35
    payload.video_segments[1].timeline_in_frame = 40
    payload.video_segments[1].timeline_out_frame = 70
    with pytest.raises(ExportError, match=r"first gap at frames 0-5"):
        common.require_timeline(payload)


def test_require_timeline_reports_the_first_audio_gap(tmp_path: Path) -> None:
    payload = state(tmp_path)
    payload.audio_segments[0].timeline_in_sample = 1600
    with pytest.raises(ExportError, match=r"first gap at samples 0-1600"):
        common.require_timeline(payload)
