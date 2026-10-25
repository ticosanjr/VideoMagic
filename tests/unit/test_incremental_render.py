"""Segment cache reuses unchanged clips and re-renders changed ones."""

from __future__ import annotations

from pathlib import Path

from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.exporters.incremental import export_mp4_incremental


class FakeAdapter:
    def __init__(self) -> None:
        self.segments = 0
        self.concats = 0

    def render(self, args, **kwargs):
        target = Path(args[-1])
        if "-f" in args and "concat" in args:
            self.concats += 1
        else:
            self.segments += 1
        target.write_bytes(b"video")


def state(tmp_path: Path, second_out: int = 60) -> ProjectState:
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
                source_out_frame=second_out,
                timeline_in_frame=30,
                timeline_out_frame=30 + (second_out - 30),
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
                source_out_sample=int(second_out / 30 * 48000),
                timeline_in_sample=48000,
                timeline_out_sample=48000 + int((second_out - 30) / 30 * 48000),
            ),
        ],
    )


def test_unchanged_segments_are_reused(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    first = export_mp4_incremental(state(tmp_path), tmp_path / "out.mp4", adapter=adapter)
    assert first.is_file()
    assert adapter.segments == 2

    export_mp4_incremental(state(tmp_path), tmp_path / "out.mp4", adapter=adapter)
    assert adapter.segments == 2
    assert adapter.concats == 2


def test_changed_clip_renders_only_that_segment(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    export_mp4_incremental(state(tmp_path), tmp_path / "out.mp4", adapter=adapter)

    export_mp4_incremental(state(tmp_path, second_out=55), tmp_path / "out.mp4", adapter=adapter)

    assert adapter.segments == 3


def test_overlays_and_fade_to_black_stay_incremental(tmp_path: Path) -> None:
    from videoflow.domain.state import OverlayClip, Transition

    overlay = tmp_path / "logo.png"
    overlay.write_bytes(b"png")
    payload = state(tmp_path)
    payload.video_segments[0].transition_out = Transition(type="fade_to_black")
    payload.overlays = [
        OverlayClip(
            overlay_id="logo",
            path=str(overlay),
            start_frame=5,
            duration_frames=20,
        )
    ]
    adapter = FakeAdapter()
    result = export_mp4_incremental(payload, tmp_path / "out.mp4", adapter=adapter)
    assert result.is_file()
    assert adapter.segments == 3  # two source segments plus the overlay pass
    assert adapter.concats == 1


def test_crossfade_renders_only_the_transition_group(tmp_path: Path) -> None:
    from videoflow.domain.state import Transition

    payload = state(tmp_path)
    payload.video_segments[0].transition_out = Transition(type="crossfade")
    adapter = FakeAdapter()
    result = export_mp4_incremental(payload, tmp_path / "out.mp4", adapter=adapter)
    assert result.is_file()
    assert adapter.segments == 3  # two cached clips plus one xfade group
    assert adapter.concats == 1

    adapter = FakeAdapter()
    export_mp4_incremental(payload, tmp_path / "out.mp4", adapter=adapter)
    assert adapter.segments == 0  # group and clip segments are reused
    assert adapter.concats == 1
