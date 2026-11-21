from __future__ import annotations

from pathlib import Path

from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState
from videoflow.exporters import mp4


def _state(tmp_path: Path) -> ProjectState:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"media")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=48_000,
    )
    return ProjectState(
        media_info=media,
        audio_segments=[
            AudioSegment(
                clip_id="a1",
                source_in_sample=0,
                source_out_sample=48_000,
                timeline_in_sample=0,
                timeline_out_sample=48_000,
            )
        ],
    )


def test_audio_filter_centers_a_unilateral_mono_channel() -> None:
    state = _state(Path("/tmp"))
    clip = state.audio_segments[0]
    filters = mp4._audio_filters(
        clip, state.media_info, mono_repair="left"  # type: ignore[arg-type]
    )
    assert "pan=stereo|c0=c0|c1=c0" in filters


def test_audio_graph_detects_the_silent_channel(tmp_path: Path, monkeypatch) -> None:
    state = _state(tmp_path)
    monkeypatch.setattr(mp4, "channel_rms", lambda path: (-8.0, -42.0))
    inputs, graph = mp4._audio_graph_inputs(
        state, state.media_info, Path(state.media_info.source_path)  # type: ignore[arg-type]
    )
    assert inputs
    assert "pan=stereo|c0=c0|c1=c0" in graph
