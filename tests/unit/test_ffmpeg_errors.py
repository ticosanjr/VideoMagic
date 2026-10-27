"""FFmpeg failures explain exit codes, signals, stderr, and commands."""

from __future__ import annotations

import pytest

from videoflow.adapters import ffmpeg
from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.domain.errors import IngestError


class Process:
    def __init__(self, returncode: int, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        return "", self.stderr


def capture(monkeypatch: pytest.MonkeyPatch, process: Process) -> IngestError:
    monkeypatch.setattr(ffmpeg, "find_binary", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(ffmpeg.subprocess, "Popen", lambda *_args, **_kwargs: process)
    with pytest.raises(IngestError) as caught:
        FFmpegAdapter()._capture(["ffmpeg", "-i", "source.mp4"])
    return caught.value


def test_sigkill_without_stderr_is_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    error = capture(monkeypatch, Process(-9))

    assert "killed by SIGKILL" in str(error)
    assert "out of memory" in str(error)
    payload = error.to_dict()
    assert payload["returncode"] == -9
    assert payload["signal"] == 9
    assert "ffmpeg" in str(payload["command"])


def test_exit_code_without_stderr_is_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    error = capture(monkeypatch, Process(1))

    assert "exit code 1" in str(error)
    assert error.to_dict()["returncode"] == 1
    assert "signal" not in error.to_dict()


def test_stderr_tail_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    error = capture(monkeypatch, Process(1, "Invalid data found\nConversion failed"))

    assert "Conversion failed" in str(error)
    assert "Invalid data found" in str(error.to_dict()["stderr"])
