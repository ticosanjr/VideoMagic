"""Persistent video-group cache used by the segmented MP4 renderer."""

from __future__ import annotations

from pathlib import Path

from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.exporters.mp4 import export_mp4


class RecordingAdapter:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def render(self, command: list[str], **kwargs: object) -> None:
        self.commands.append(list(command))
        Path(command[-1]).write_bytes(b"mp4")


def state(tmp_path: Path) -> ProjectState:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=600,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )
    video = []
    audio = []
    for index in range(20):
        start = index * 6
        video.append(
            VideoSegment(
                clip_id=f"v{index}",
                source_in_frame=start,
                source_out_frame=start + 6,
                timeline_in_frame=start,
                timeline_out_frame=start + 6,
            )
        )
        audio.append(
            AudioSegment(
                clip_id=f"v{index}",
                source_in_sample=start * 1600,
                source_out_sample=(start + 6) * 1600,
                timeline_in_sample=start * 1600,
                timeline_out_sample=(start + 6) * 1600,
            )
        )
    return ProjectState(media_info=media, video_segments=video, audio_segments=audio)


def group_commands(commands: list[list[str]]) -> list[list[str]]:
    return [
        command
        for command in commands
        if "-filter_complex" in command and "[c0]" in " ".join(command)
    ]


def test_unchanged_groups_are_reused(tmp_path: Path) -> None:
    payload = state(tmp_path)
    first_adapter = RecordingAdapter()
    destination = tmp_path / "out.mp4"

    export_mp4(payload, destination, adapter=first_adapter)
    assert len(group_commands(first_adapter.commands)) == 20
    assert (tmp_path / "segments").is_dir()

    second_adapter = RecordingAdapter()
    export_mp4(payload, destination, adapter=second_adapter)
    assert group_commands(second_adapter.commands) == []
    assert destination.is_file()


def test_scale_changes_invalidate_the_group_cache(tmp_path: Path) -> None:
    payload = state(tmp_path)
    first_adapter = RecordingAdapter()
    export_mp4(payload, tmp_path / "out.mp4", adapter=first_adapter)

    scaled_adapter = RecordingAdapter()
    export_mp4(
        payload,
        tmp_path / "scaled.mp4",
        adapter=scaled_adapter,
        scale_height=240,
    )

    assert len(group_commands(scaled_adapter.commands)) == 20
    graphs = [
        command[command.index("-filter_complex") + 1]
        for command in group_commands(scaled_adapter.commands)
    ]
    assert any("scale=-2:240" in graph for graph in graphs)
