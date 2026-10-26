"""MP4 exporter: filter-graph branches, overlays, progress, and failures."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.contract.test_exporters import sample_state
from videoflow.domain.errors import ExportError
from videoflow.domain.state import OverlayClip, ProjectState, Transition
from videoflow.exporters.mp4 import build_filter_graph, export_mp4


class FakeRenderer:
    def __init__(self, *, write: bool = True) -> None:
        self.write = write
        self.commands: list[list[str]] = []
        self.progress_calls = 0

    def render(self, command: list[str], progress: object = None) -> None:
        self.commands.append(command)
        if progress is not None:
            progress(5)  # type: ignore[operator]
            self.progress_calls += 1
        if self.write:
            Path(command[-1]).write_bytes(b"mp4")


def test_crossfade_graph_handles_missing_audio_transitions(tmp_path: Path) -> None:
    state = sample_state(tmp_path)
    state.video_segments[0].transition_out = Transition(audio=False)
    state.video_segments[1].transition_out = None

    graph, video_label, audio_label = build_filter_graph(state)

    assert "xfade=transition=fade" in graph
    assert "concat=n=2:v=0:a=1" in graph
    assert video_label.startswith("[")
    assert audio_label.startswith("[")


def test_export_mp4_requires_media(tmp_path: Path) -> None:
    state = ProjectState()

    with pytest.raises(ExportError, match="no media"):
        export_mp4(state, tmp_path / "out.mp4")


def test_export_mp4_wires_filters_ass_and_overlays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = sample_state(tmp_path)
    image = tmp_path / "logo.png"
    image.write_bytes(b"png")
    video = tmp_path / "overlay.mp4"
    video.write_bytes(b"mp4")
    state.overlays = [
        OverlayClip(
            overlay_id="o1",
            path=str(image),
            start_frame=0,
            duration_frames=30,
            kind="image",
        ),
        OverlayClip(
            overlay_id="o2",
            path=str(video),
            start_frame=30,
            duration_frames=30,
            kind="video",
        ),
        OverlayClip(
            overlay_id="o3",
            path=str(tmp_path / "missing.png"),
            start_frame=0,
            duration_frames=10,
        ),
    ]
    ass = tmp_path / "titles.ass"
    ass.write_text("[Script Info]", encoding="utf-8")
    renderer = FakeRenderer()

    target = export_mp4(
        state,
        tmp_path / "out.mp4",
        adapter=renderer,  # type: ignore[arg-type]
        audio_filters=["volume=0.5"],
        video_filters=["eq=contrast=1.2"],
        ass_path=ass,
        progress=lambda percent: None,
    )

    assert target.is_file()
    assert renderer.progress_calls == 1
    command = renderer.commands[0]
    graph = command[command.index("-filter_complex") + 1]
    assert "volume=0.5" in graph
    assert "eq=contrast=1.2" in graph
    assert "ass=" in graph
    assert "-loop" in command
    assert "-stream_loop" in command


def test_export_mp4_without_progress_and_missing_output(
    tmp_path: Path,
) -> None:
    state = sample_state(tmp_path)
    renderer = FakeRenderer(write=False)

    with pytest.raises(ExportError, match="did not write"):
        export_mp4(state, tmp_path / "out.mp4", adapter=renderer)  # type: ignore[arg-type]

    assert renderer.progress_calls == 0
