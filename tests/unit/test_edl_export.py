from __future__ import annotations

from pathlib import Path

from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    VideoSegment,
)
from videoflow.exporters.edl import export_edl


def _state(tmp_path: Path) -> ProjectState:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    return ProjectState(
        media_info=MediaInfo(
            source_path=str(source),
            duration_frames=60,
            fps_num=30,
            fps_den=1,
            width=1920,
            height=1080,
            audio_sample_rate=48000,
        ),
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


def test_edl_export_writes_cmx_events(tmp_path: Path) -> None:
    target = export_edl(_state(tmp_path), tmp_path / "timeline.edl")
    text = target.read_text()
    assert "TITLE: VideoFlow" in text
    assert "FCM: NON-DROP FRAME" in text
    assert "001  AX       V     C        00:00:00:00 00:00:01:00 00:00:00:00 00:00:01:00" in text
    assert "002  AX       V     C        00:00:01:00 00:00:02:00 00:00:01:00 00:00:02:00" in text
    assert "* FROM CLIP NAME: source.mp4" in text
    assert "* TOTAL DURATION: 00:00:02:00" in text
