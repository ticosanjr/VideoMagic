from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videoflow.application.audio_finalize import finalize_audio
from videoflow.application.compute import guard_remote_policy
from videoflow.core.media_contract import (
    channel_rms,
    needs_mono_repair,
    repair_mono_file,
    source_needs_normalization,
    validate_media,
)

FFMPEG = shutil.which("ffmpeg")


def _run(*args: str) -> None:
    assert FFMPEG is not None
    completed = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def _left_only(path: Path) -> Path:
    _run(
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=2",
        "-af",
        "pan=stereo|c0=c0|c1=0*c0",
        "-c:a",
        "pcm_s24le",
        str(path),
    )
    return path


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_channel_rms_and_mono_repair(tmp_path: Path) -> None:
    path = _left_only(tmp_path / "left.wav")
    left, right = channel_rms(path)
    assert left > right + 18
    assert needs_mono_repair(left, right) == "left"
    assert repair_mono_file(path) is True
    left2, right2 = channel_rms(path)
    assert abs(left2 - right2) < 1.0
    assert validate_media(path, "audio_master").ok


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_audio_finalize_keeps_exact_duration(tmp_path: Path) -> None:
    voice = tmp_path / "voice.wav"
    _run(
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=2.4",
        "-ac",
        "2",
        "-c:a",
        "pcm_s24le",
        str(voice),
    )
    result = finalize_audio(voice, tmp_path / "project", duration_sec=2.4)
    payload = validate_media(result.path, "audio_master")
    assert payload.ok, payload.to_dict()
    assert abs(float(payload.metrics["format"]["duration_sec"]) - 2.4) < 0.01


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_source_normalization_flags_ten_bit_422(tmp_path: Path) -> None:
    path = tmp_path / "tenbit.mkv"
    _run(
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=1920x1080:rate=30:duration=1",
        "-c:v",
        "ffv1",
        "-pix_fmt",
        "yuv422p10le",
        str(path),
    )
    assert "pixel_format" in source_needs_normalization(path)


class _Router:
    def __init__(self, remote: bool) -> None:
        self.remote = remote

    def decide(self, capability: str):
        class Decision:
            is_remote = self.remote
            reason = "worker offline" if not self.remote else "remote"

        return Decision()


def test_guard_remote_policy_fails_fast_without_fallback() -> None:
    with pytest.raises(RuntimeError, match="gpu_required_for_operation"):
        guard_remote_policy(
            _Router(False),  # type: ignore[arg-type]
            "asr",
            compute_policy="remote",
        )
    guard_remote_policy(
        _Router(False),  # type: ignore[arg-type]
        "asr",
        compute_policy="remote",
        allow_slow_cpu_fallback=True,
    )
    guard_remote_policy(
        _Router(False),  # type: ignore[arg-type]
        "asr",
        compute_policy="auto",
    )
