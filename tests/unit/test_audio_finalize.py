from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videoflow.core.media_contract import validate_media
from videoflow.domains.audio.finalize import finalize_audio

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


def _voice(path: Path, *, left_only: bool = False) -> Path:
    source = "sine=frequency=440:sample_rate=48000:duration=2"
    if left_only:
        _run(
            "-f",
            "lavfi",
            "-i",
            source,
            "-af",
            "pan=stereo|c0=c0|c1=0*c0",
            "-c:a",
            "pcm_s24le",
            str(path),
        )
    else:
        _run(
            "-f",
            "lavfi",
            "-i",
            source,
            "-ac",
            "2",
            "-c:a",
            "pcm_s24le",
            str(path),
        )
    return path


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_finalize_audio_writes_48k_24bit_at_target_loudness(tmp_path: Path) -> None:
    voice = _voice(tmp_path / "voice.wav")
    result = finalize_audio(voice, tmp_path / "project", duration_sec=2.0)

    assert result.ok
    assert result.mono_repaired is False
    assert Path(result.path).is_file()
    assert abs(result.integrated_lufs + 16.0) <= 1.5
    report = validate_media(result.path, "audio_master")
    assert report.ok, report.to_dict()
    assert report.metrics["audio"]["sample_rate"] == 48000
    assert report.metrics["audio"]["channels"] == 2
    assert report.metrics["audio"]["codec"] == "pcm_s24le"


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_finalize_audio_repairs_left_only_mono(tmp_path: Path) -> None:
    voice = _voice(tmp_path / "left.wav", left_only=True)
    result = finalize_audio(voice, tmp_path / "project", duration_sec=2.0)

    assert result.ok
    assert result.mono_repaired is True
    assert any("left channel" in warning for warning in result.warnings)


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_finalize_audio_mixes_music_and_foley(tmp_path: Path) -> None:
    voice = _voice(tmp_path / "voice.wav")
    music = tmp_path / "music.wav"
    _run(
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=220:sample_rate=44100:duration=1",
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(music),
    )
    sfx = tmp_path / "sfx.wav"
    _run(
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=880:sample_rate=48000:duration=0.2",
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(sfx),
    )
    result = finalize_audio(
        voice,
        tmp_path / "project",
        music_path=music,
        sfx_path=sfx,
        duration_sec=2.0,
    )

    assert result.ok
    assert Path(result.path).is_file()
    assert abs(result.integrated_lufs + 16.0) <= 1.5
