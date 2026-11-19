from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application.delivery_bundle import _fps_value, _mp4_metadata, timeline_frames
from videoflow.application.qa_word_fidelity import verify_word_fidelity
from videoflow.domain.errors import ExportError
from videoflow.domain.state import ProjectState, Sentence
from videoflow.exporters import mp4
from videoflow.exporters.mp4 import (
    _expected_seconds,
    _video_groups,
    _write_export_layout,
    build_filter_graph,
    output_render_frames,
    video_encoder,
)


def test_fps_value_normalizes_source_and_invalid_values() -> None:
    assert _fps_value(None) is None
    assert _fps_value("source") is None
    assert _fps_value("auto") is None
    assert _fps_value("") is None
    assert _fps_value("30") == 30
    assert _fps_value("bad") is None
    assert _fps_value(0) is None
    assert _fps_value(24) == 24
    assert timeline_frames(ProjectState()) == 0


def test_mp4_metadata_reports_missing_file(tmp_path: Path) -> None:
    assert _mp4_metadata(tmp_path / "missing.mp4") == {"exists": False}


def test_export_helpers_cover_empty_timelines() -> None:
    state = ProjectState()
    assert _expected_seconds(state) == 0.0
    assert _video_groups([]) == []
    _write_export_layout(state, Path("/tmp/none.mp4"))
    with pytest.raises(ExportError):
        build_filter_graph(state)
    with pytest.raises(ExportError):
        mp4._render_classic_mp4(state, Path("/tmp/none.mp4"))


def test_video_encoder_env_choices(monkeypatch) -> None:
    video_encoder.cache_clear()
    monkeypatch.setenv("VF_VIDEO_ENCODER", "nvenc")
    assert video_encoder() == "h264_nvenc"
    video_encoder.cache_clear()
    monkeypatch.setenv("VF_VIDEO_ENCODER", "cpu")
    assert video_encoder() == "libx264"
    video_encoder.cache_clear()
    monkeypatch.setenv("VF_VIDEO_ENCODER", "weird")
    assert video_encoder() == "libx264"
    video_encoder.cache_clear()
    monkeypatch.setenv("VF_VIDEO_ENCODER", "auto")
    monkeypatch.setattr(mp4.shutil, "which", lambda name: None)
    assert video_encoder() == "libx264"


def test_video_encoder_auto_detects_nvenc(monkeypatch) -> None:
    class Probe:
        returncode = 0
        stdout = "NVIDIA GeForce RTX 3060\n"

    class Encoders:
        returncode = 0
        stdout = " V....D h264_nvenc"

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return Probe() if "nvidia-smi" in command[0] else Encoders()

    monkeypatch.setenv("VF_VIDEO_ENCODER", "auto")
    monkeypatch.setattr(mp4.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(mp4.subprocess, "run", fake_run)
    video_encoder.cache_clear()
    assert video_encoder() == "h264_nvenc"
    assert any("nvidia-smi" in command[0] for command in calls)
    video_encoder.cache_clear()

    class BrokenProbe:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(
        mp4.subprocess,
        "run",
        lambda command, **kwargs: BrokenProbe(),
    )
    assert video_encoder() == "libx264"
    video_encoder.cache_clear()


def test_output_render_frames_without_media_state() -> None:
    assert output_render_frames(ProjectState(), 30) == 0


def test_word_fidelity_unavailable_backend(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application.qa_word_fidelity import _DEFAULT_ALIASES

    assert "hwang" in _DEFAULT_ALIASES
    monkeypatch.setattr(
        "videoflow.adapters.faster_whisper.FasterWhisperAdapter.available",
        staticmethod(lambda **kwargs: False),
    )
    result = verify_word_fidelity(
        tmp_path / "x.mp4",
        [Sentence(id=0, start_sample=0, end_sample=1, text="texto")],
        work=tmp_path,
    )
    assert result["status"] == "unavailable"
    assert result["passed"] is True
