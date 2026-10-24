"""Large-timeline stress checks for the NLE writers."""

from __future__ import annotations

import time
from pathlib import Path

from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.exporters.fcpxml import export_fcpxml
from videoflow.exporters.kdenlive import export_kdenlive
from videoflow.exporters.xmeml import export_xmeml

CLIPS = 1000


def large_state(tmp_path: Path) -> ProjectState:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=CLIPS * 30,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=48000,
    )
    video = []
    audio = []
    for index in range(CLIPS):
        start = index * 30
        video.append(
            VideoSegment(
                clip_id=f"v{index}",
                source_in_frame=start,
                source_out_frame=start + 30,
                timeline_in_frame=start,
                timeline_out_frame=start + 30,
            )
        )
        audio.append(
            AudioSegment(
                clip_id=f"v{index}",
                source_in_sample=start * 1600,
                source_out_sample=(start + 30) * 1600,
                timeline_in_sample=start * 1600,
                timeline_out_sample=(start + 30) * 1600,
            )
        )
    return ProjectState(media_info=media, video_segments=video, audio_segments=audio)


def test_writers_handle_one_thousand_clips(tmp_path: Path) -> None:
    state = large_state(tmp_path)
    timings: dict[str, float] = {}

    started = time.perf_counter()
    fcpxml = export_fcpxml(state, tmp_path / "timeline.fcpxml")
    timings["fcpxml"] = time.perf_counter() - started

    started = time.perf_counter()
    xmeml = export_xmeml(state, tmp_path / "timeline.xml")
    timings["xmeml"] = time.perf_counter() - started

    started = time.perf_counter()
    kdenlive = export_kdenlive(state, tmp_path / "timeline.kdenlive")
    timings["kdenlive"] = time.perf_counter() - started

    for path in (fcpxml, xmeml, kdenlive):
        assert path.is_file()
        assert path.stat().st_size > 10_000
    for name, seconds in timings.items():
        assert seconds < 10.0, f"{name} took {seconds:.2f}s"


def test_large_timeline_duration(tmp_path: Path) -> None:
    from videoflow.exporters.common import timeline_duration_frames

    state = large_state(tmp_path)
    assert timeline_duration_frames(state) == CLIPS * 30
