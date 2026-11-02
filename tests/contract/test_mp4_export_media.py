"""Real FFmpeg MP4 export for long hard-cut timelines.

The regression is the 44-clip OOM: a single monolithic filter graph loaded the
whole 1080p timeline at once. Long timelines must use the segmented exporter.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.shorts import CaptionStyle, build_ass
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    OverlayClip,
    ProjectState,
    VideoSegment,
)
from videoflow.exporters.mp4 import export_mp4

pytestmark = pytest.mark.media


class RecordingAdapter(FFmpegAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.commands: list[list[str]] = []

    def render(self, args: list[str], **kwargs: object) -> None:
        self.commands.append(list(args))
        super().render(args, **kwargs)  # type: ignore[arg-type]


def source(tmp_path: Path) -> Path:
    path = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=6",
            "-t",
            "6",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )
    return path


def state_for(media: MediaInfo, clips: int = 20) -> ProjectState:
    frames = 6
    samples = 9600
    return ProjectState(
        media_info=media,
        video_segments=[
            VideoSegment(
                clip_id=f"v{index}",
                source_in_frame=0,
                source_out_frame=frames,
                timeline_in_frame=index * frames,
                timeline_out_frame=(index + 1) * frames,
            )
            for index in range(clips)
        ],
        audio_segments=[
            AudioSegment(
                clip_id=f"v{index}",
                source_in_sample=0,
                source_out_sample=samples,
                timeline_in_sample=index * samples,
                timeline_out_sample=(index + 1) * samples,
            )
            for index in range(clips)
        ],
    )


def test_long_hard_cut_timeline_exports_without_a_giant_graph(tmp_path: Path) -> None:
    media = FFmpegAdapter().probe(source(tmp_path))
    adapter = RecordingAdapter()

    result = export_mp4(state_for(media), tmp_path / "out.mp4", adapter=adapter)

    assert result.is_file()
    assert result.stat().st_size > 0
    assert adapter.commands
    for command in adapter.commands:
        if "-filter_complex" in command:
            graph = command[command.index("-filter_complex") + 1]
            assert graph.count("trim=start_frame") <= 1
    rendered = FFmpegAdapter().probe(result)
    assert abs(rendered.duration_frames - 120) <= 2
    assert rendered.audio_sample_rate == 48000


def test_segmented_export_keeps_filters_titles_and_overlays(tmp_path: Path) -> None:
    media = FFmpegAdapter().probe(source(tmp_path))
    state = state_for(media, clips=18)
    overlay = tmp_path / "overlay.png"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:size=32x32",
            "-frames:v",
            "1",
            str(overlay),
        ],
        check=True,
    )
    state.overlays = [
        OverlayClip(
            overlay_id="o1",
            path=str(overlay),
            start_frame=0,
            duration_frames=60,
            opacity=0.7,
        )
    ]
    ass = tmp_path / "titles.ass"
    ass.write_text(
        build_ass([(0.0, 1.0, "Segment test")], style=CaptionStyle(), width=640, height=360),
        encoding="utf-8",
    )
    adapter = RecordingAdapter()

    result = export_mp4(
        state,
        tmp_path / "finished.mp4",
        adapter=adapter,
        video_filters=["eq=contrast=1.1"],
        audio_filters=["volume=0.9"],
        ass_path=ass,
    )

    assert result.is_file()
    rendered = FFmpegAdapter().probe(result)
    assert rendered.duration_frames >= 100
    final_commands = [
        command for command in adapter.commands if "-filter_complex" in command
    ]
    graphs = [
        command[command.index("-filter_complex") + 1] for command in final_commands
    ]
    assert any("overlay=" in graph for graph in graphs)
    assert any("ass=" in graph for graph in graphs)


def test_long_crossfade_timeline_uses_segmented_groups(tmp_path: Path) -> None:
    from videoflow.domain.state import Transition

    media = FFmpegAdapter().probe(source(tmp_path))
    state = state_for(media, clips=18)
    for clip in state.video_segments[:-1]:
        clip.transition_out = Transition(type="crossfade", duration_frames=2)
    adapter = RecordingAdapter()

    result = export_mp4(state, tmp_path / "crossfade.mp4", adapter=adapter)

    assert result.is_file()
    group_commands = [
        command
        for command in adapter.commands
        if "-filter_complex" in command and "[c0]" in " ".join(command)
    ]
    assert group_commands
    assert any("xfade=transition=fade" in " ".join(command) for command in group_commands)
    assert any("-ss" in command for command in group_commands)
    rendered = FFmpegAdapter().probe(result)
    assert abs(rendered.duration_frames - 74) <= 3
    assert rendered.audio_sample_rate == 48000


def test_crossfade_timeline_keeps_finishing_filters(tmp_path: Path) -> None:
    from videoflow.domain.state import Transition

    media = FFmpegAdapter().probe(source(tmp_path))
    state = state_for(media, clips=6)
    for clip in state.video_segments[:-1]:
        clip.transition_out = Transition(type="crossfade", duration_frames=2)
    state.video_segments[2].transition_out = Transition(
        type="crossfade", duration_frames=2, audio=False
    )
    overlay = tmp_path / "overlay.png"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:size=32x32",
            "-frames:v",
            "1",
            str(overlay),
        ],
        check=True,
    )
    state.overlays = [
        OverlayClip(
            overlay_id="o1",
            path=str(overlay),
            start_frame=0,
            duration_frames=12,
            opacity=0.7,
        )
    ]
    ass = tmp_path / "titles.ass"
    ass.write_text(
        build_ass([(0.0, 1.0, "Crossfade")], style=CaptionStyle(), width=640, height=360),
        encoding="utf-8",
    )
    adapter = RecordingAdapter()

    result = export_mp4(
        state,
        tmp_path / "crossfade-finished.mp4",
        adapter=adapter,
        video_filters=["eq=contrast=1.1"],
        audio_filters=["volume=0.9"],
        ass_path=ass,
    )

    assert result.is_file()
    rendered = FFmpegAdapter().probe(result)
    assert abs(rendered.duration_frames - 26) <= 3
    graphs = [
        command[command.index("-filter_complex") + 1]
        for command in adapter.commands
        if "-filter_complex" in command
    ]
    assert any("overlay=" in graph for graph in graphs)
    assert any("ass=" in graph for graph in graphs)


def test_incremental_export_seeks_and_reuses_segments(tmp_path: Path) -> None:
    from videoflow.exporters.incremental import export_mp4_incremental

    media = FFmpegAdapter().probe(source(tmp_path))
    state = state_for(media, clips=20)
    for index, clip in enumerate(state.video_segments):
        clip.source_in_frame = index * 3
        clip.source_out_frame = index * 3 + 6
    for index, clip in enumerate(state.audio_segments):
        clip.source_in_sample = index * 4800
        clip.source_out_sample = index * 4800 + 9600
    adapter = RecordingAdapter()

    first = export_mp4_incremental(
        state, tmp_path / "incremental.mp4", adapter=adapter
    )

    assert first.is_file()
    segment_commands = [command for command in adapter.commands if "-ss" in command]
    assert len(segment_commands) == 20
    for command in segment_commands:
        assert command.index("-ss") < command.index("-i")
    rendered = FFmpegAdapter().probe(first)
    assert abs(rendered.duration_frames - 120) <= 2

    cached_adapter = RecordingAdapter()
    second = export_mp4_incremental(
        state, tmp_path / "incremental.mp4", adapter=cached_adapter
    )

    assert second.is_file()
    assert not [command for command in cached_adapter.commands if "-ss" in command]
