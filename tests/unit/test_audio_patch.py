"""Audio patch command construction."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.application import audio_patch


def test_patch_audio_builds_crossfaded_command(tmp_path: Path, monkeypatch) -> None:
    master = tmp_path / "master.wav"
    patch = tmp_path / "line.wav"
    master.write_bytes(b"master")
    patch.write_bytes(b"patch")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        if "ffprobe" in str(command[0]):
            return SimpleNamespace(returncode=0, stdout="2.0\n", stderr="")
        target = Path(command[-1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"out")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(audio_patch, "find_binary", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(audio_patch.subprocess, "run", fake_run)
    result = audio_patch.patch_audio(
        master,
        patch,
        start_sec=1.0,
        end_sec=2.0,
        output=tmp_path / "patched.wav",
        crossfade_ms=50,
    )
    assert Path(result["path"]).is_file()
    assert "afade" in " ".join(captured["command"])  # type: ignore[arg-type]


def test_patch_audio_rejects_bad_range(tmp_path: Path) -> None:
    master = tmp_path / "master.wav"
    patch = tmp_path / "line.wav"
    master.write_bytes(b"x")
    patch.write_bytes(b"y")
    with pytest.raises(ValueError):
        audio_patch.patch_audio(
            master, patch, start_sec=3, end_sec=2, output=tmp_path / "out.wav"
        )
