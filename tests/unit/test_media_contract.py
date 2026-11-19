from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videoflow.core.media_contract import (
    MediaContractError,
    assert_media,
    color_profile,
    validate_alpha,
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


def _wav(path: Path, *, rate: int = 48000, channels: int = 2, codec: str = "pcm_s24le") -> Path:
    _run(
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:sample_rate={rate}:duration=1",
        "-ac",
        str(channels),
        "-c:a",
        codec,
        str(path),
    )
    return path


def _video(path: Path, *, fps: int = 30, pix_fmt: str = "yuv420p") -> Path:
    _run(
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size=320x240:rate={fps}:duration=1",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=1",
        "-c:v",
        "libx264",
        "-pix_fmt",
        pix_fmt,
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(path),
    )
    return path


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_audio_master_accepts_48k_stereo_24bit(tmp_path: Path) -> None:
    path = _wav(tmp_path / "master.wav")
    report = validate_media(path, "audio_master")
    assert report.ok, report.to_dict()
    assert report.metrics["audio"]["sample_rate"] == 48000
    assert report.metrics["audio"]["channels"] == 2
    assert report.metrics["audio"]["codec"] == "pcm_s24le"


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_audio_master_rejects_mono_44k_16bit(tmp_path: Path) -> None:
    path = _wav(tmp_path / "bad.wav", rate=44100, channels=1, codec="pcm_s16le")
    report = validate_media(path, "audio_master")
    codes = {item["code"] for item in report.errors}
    assert "audio_sample_rate" in codes
    assert "audio_channels" in codes
    assert "audio_codec" in codes


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_overlay_requires_alpha(tmp_path: Path) -> None:
    from PIL import Image

    rgba = tmp_path / "alpha.png"
    Image.new("RGBA", (64, 64), (255, 0, 0, 128)).save(rgba)
    assert validate_alpha(rgba).ok

    rgb = tmp_path / "opaque.png"
    Image.new("RGB", (64, 64), (255, 0, 0)).save(rgb)
    report = validate_alpha(rgb)
    assert not report.ok
    assert report.errors[0]["code"] == "alpha_channel_missing"


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_deliverable_contract_and_assert(tmp_path: Path) -> None:
    path = _video(tmp_path / "deliverable.mp4")
    report = validate_media(path, "deliverable")
    assert report.ok, report.to_dict()
    assert report.metrics["video"]["fps"] == 30.0
    assert report.metrics["audio"]["sample_rate"] == 48000

    with pytest.raises(MediaContractError) as error:
        assert_media(tmp_path / "missing.mp4", "deliverable")
    assert error.value.code == "media_not_found"


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_color_profile_flags_ten_bit_422(tmp_path: Path) -> None:
    path = tmp_path / "tenbit.mkv"
    _run(
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=320x240:rate=30:duration=1",
        "-c:v",
        "ffv1",
        "-pix_fmt",
        "yuv422p10le",
        str(path),
    )
    profile = color_profile(path)
    assert profile["ten_bit"] is True
    assert profile["needs_cpu_decode"] is True
