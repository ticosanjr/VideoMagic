"""MP4 exporter: filter-graph branches, overlays, progress, and failures."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.contract.test_exporters import sample_state
from videoflow.domain.errors import ExportError
from videoflow.domain.state import OverlayClip, ProjectState, Transition
from videoflow.exporters import mp4 as mp4_module
from videoflow.exporters.mp4 import export_mp4


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


def test_large_hard_cut_timeline_uses_segmented_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = sample_state(tmp_path)
    state.video_segments = [
        state.video_segments[0].model_copy(
            update={
                "clip_id": f"v{index}",
                "source_in_frame": 0,
                "source_out_frame": 10,
                "timeline_in_frame": index * 10,
                "timeline_out_frame": index * 10 + 10,
            }
        )
        for index in range(17)
    ]
    state.audio_segments = []
    called: list[bool] = []
    expected = tmp_path / "segmented.mp4"

    def fake_segmented(*_args: object, **_kwargs: object) -> Path:
        called.append(True)
        expected.write_bytes(b"mp4")
        return expected

    monkeypatch.setattr(mp4_module, "_export_mp4_segmented", fake_segmented)

    result = export_mp4(state, expected)

    assert called == [True]
    assert result == expected


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


def test_large_crossfade_timeline_uses_bounded_groups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.domain.state import VideoSegment

    state = sample_state(tmp_path)
    state.video_segments = [
        VideoSegment(
            clip_id=f"v{index}",
            source_in_frame=0,
            source_out_frame=10,
            timeline_in_frame=index * 10,
            timeline_out_frame=index * 10 + 10,
            transition_out=Transition(type="crossfade", duration_frames=3)
            if index in {0, 2}
            else None,
        )
        for index in range(17)
    ]
    state.audio_segments = []
    renderer = FakeRenderer()

    # The segmented renderer needs a matching audio/video count; reuse the
    # source ranges with equally short audio clips.
    from videoflow.domain.state import AudioSegment

    state.audio_segments = [
        AudioSegment(
            clip_id=f"v{index}",
            source_in_sample=0,
            source_out_sample=1600,
            timeline_in_sample=index * 1600,
            timeline_out_sample=index * 1600 + 1600,
        )
        for index in range(17)
    ]

    result = export_mp4(state, tmp_path / "crossfade.mp4", adapter=renderer)

    assert result.is_file()
    group_commands = [
        command
        for command in renderer.commands
        if "-filter_complex" in command and "[c0]" in " ".join(command)
    ]
    assert len(group_commands) == 15  # two pair groups plus 15 singles
    assert any("xfade=transition=fade" in " ".join(command) for command in group_commands)
    assert any("-ss" in command for command in group_commands)
    # Audio crossfades follow the video groups.
    audio_command = next(command for command in renderer.commands if "[aout]" in " ".join(command))
    assert "acrossfade=d=" in " ".join(audio_command)


def test_audio_only_filters_do_not_reencode_video(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = sample_state(tmp_path)
    state.video_segments = [
        state.video_segments[0].model_copy(
            update={
                "clip_id": f"v{index}",
                "source_in_frame": 0,
                "source_out_frame": 10,
                "timeline_in_frame": index * 10,
                "timeline_out_frame": index * 10 + 10,
            }
        )
        for index in range(17)
    ]
    state.audio_segments = []
    from videoflow.domain.state import AudioSegment

    state.audio_segments = [
        AudioSegment(
            clip_id=f"v{index}",
            source_in_sample=0,
            source_out_sample=1600,
            timeline_in_sample=index * 1600,
            timeline_out_sample=index * 1600 + 1600,
        )
        for index in range(17)
    ]
    renderer = FakeRenderer()

    export_mp4(
        state,
        tmp_path / "audio-filtered.mp4",
        adapter=renderer,
        audio_filters=["volume=0.5"],
    )

    video_commands = [command for command in renderer.commands if "-c:v" in command]
    assert len(video_commands) == 17
    audio_commands = [command for command in renderer.commands if "[afinal]" in " ".join(command)]
    assert audio_commands
    assert "volume=0.5" in " ".join(audio_commands[0])


def test_zoom_expression_uses_a_hold_envelope() -> None:
    from videoflow.domain.state import TransformKeyframe
    from videoflow.exporters.mp4 import _zoom_expression

    expression = _zoom_expression(
        [
            TransformKeyframe(at=0.0, scale=1.0),
            TransformKeyframe(at=0.2, scale=1.08),
            TransformKeyframe(at=0.8, scale=1.08),
            TransformKeyframe(at=1.0, scale=1.0),
        ],
        59,
    )
    assert "if(lt(on," in expression
    assert "clip(" in expression
    assert "1.08" in expression


def test_zoom_filters_oversample_and_align_pixels(tmp_path: Path) -> None:
    from videoflow.domain.state import Transform, TransformKeyframe
    from videoflow.exporters.mp4 import _transform_filters

    state = sample_state(tmp_path)
    clip = state.video_segments[0].model_copy(
        update={
            "transform": Transform(
                type="slow_zoom_in",
                scale=1.08,
                keyframes=[
                    TransformKeyframe(at=0.0, scale=1.0),
                    TransformKeyframe(at=1.0, scale=1.08),
                ],
            )
        }
    )
    filters = _transform_filters(clip, state.media_info)
    chain = ",".join(filters)
    assert "zoompan=" in chain
    assert "trunc((iw-iw/zoom)/2/2)*2" in chain
    assert f"scale={state.media_info.width * 2}:{state.media_info.height * 2}" in chain
    assert f"scale={state.media_info.width}:{state.media_info.height}:flags=lanczos" in chain
    assert chain.endswith("setsar=1")


def test_punch_in_uses_stable_scale_and_crop(tmp_path: Path) -> None:
    from videoflow.domain.state import Transform
    from videoflow.exporters.mp4 import _transform_filters

    state = sample_state(tmp_path)
    clip = state.video_segments[0].model_copy(
        update={"transform": Transform(type="punch_in", scale=1.08)}
    )
    chain = ",".join(_transform_filters(clip, state.media_info))
    assert "zoompan=" not in chain
    assert "crop=" in chain
    assert chain.endswith("setsar=1")

    sampled = state.video_segments[0].model_copy(
        update={"transform": Transform(type="punch_in", scale=1.2)}
    )
    chain = ",".join(_transform_filters(sampled, state.media_info))
    expected_width = round(state.media_info.width * 1.2 / 2) * 2
    expected_height = round(state.media_info.height * 1.2 / 2) * 2
    assert f"scale={expected_width}:{expected_height}" in chain
    assert "crop=" in chain and "setsar=1" in chain


def test_export_timeline_audio_uses_the_timeline_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.exporters.mp4 import export_timeline_audio

    state = sample_state(tmp_path)
    renderer = FakeRenderer()
    target = tmp_path / "timeline.wav"
    export_timeline_audio(
        state,
        target,
        adapter=renderer,
        audio_filters=("loudnorm=I=-16",),
        sample_rate=44100,
    )

    command = renderer.commands[-1]
    assert "-filter_complex" in command
    assert "loudnorm=I=-16" in " ".join(command)
    assert command[command.index("-ar") + 1] == "44100"
    assert target.read_bytes() == b"mp4"

    state.video_segments = []
    state.audio_segments = []
    with pytest.raises(ExportError, match="clip mismatch|no audio|no video"):
        export_timeline_audio(state, tmp_path / "empty.wav", adapter=renderer)
