from __future__ import annotations

from pathlib import Path

from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    VideoSegment,
)
from videoflow.exporters.mp4 import export_mp4, output_render_frames


def _state(tmp_path: Path, fps: int = 60) -> ProjectState:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    frames = fps * 10
    samples = 48000 * 10
    return ProjectState(
        media_info=MediaInfo(
            source_path=str(source),
            duration_frames=frames,
            fps_num=fps,
            fps_den=1,
            width=1920,
            height=1080,
            audio_sample_rate=48000,
        ),
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_in_frame=0,
                source_out_frame=frames,
                timeline_in_frame=0,
                timeline_out_frame=frames,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_in_sample=0,
                source_out_sample=samples,
                timeline_in_sample=0,
                timeline_out_sample=samples,
            )
        ],
    )


def test_output_render_frames_preserves_duration(tmp_path: Path) -> None:
    state = _state(tmp_path, fps=60)
    assert output_render_frames(state, None) == 600
    assert output_render_frames(state, 30) == 300
    assert output_render_frames(state, 24) == 240


def test_export_mp4_uses_the_requested_output_fps(tmp_path: Path) -> None:
    state = _state(tmp_path, fps=60)
    destination = tmp_path / "out.mp4"
    commands: list[list[str]] = []

    class FakeAdapter:
        def render(self, args, **kwargs):
            commands.append(list(args))
            Path(args[-1]).write_bytes(b"mp4")

    export_mp4(state, destination, adapter=FakeAdapter(), fps=30)
    assert destination.is_file()
    assert commands
    command = commands[0]
    assert "-r" in command
    assert command[command.index("-r") + 1] == "30/1"
    assert "-t" in command
    assert command[command.index("-t") + 1] == "10.000000"
