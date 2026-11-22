from __future__ import annotations

import wave
from pathlib import Path

import pytest

from videoflow.application.alignment import _Rms, decode_pcm_mono_rms

RATE = 48_000


def _wav_24bit(path: Path, value: int = 1000, frames: int = 480) -> Path:
    sample = int(value << 8).to_bytes(3, "little", signed=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(3)
        handle.setframerate(RATE)
        handle.writeframes(sample * frames)
    return path


def test_24bit_pcm_rms_is_not_silent(tmp_path: Path) -> None:
    path = _wav_24bit(tmp_path / "voice24.wav")
    rms = _Rms(path, RATE)
    try:
        assert rms.width == 3
        assert rms(0, 480) > 900
    finally:
        rms.close()


def test_24bit_helper_truncates_an_incomplete_frame() -> None:
    data = (int(1000 << 8).to_bytes(3, "little", signed=True)) * 2 + b"\x7f"
    assert decode_pcm_mono_rms(data, sampwidth=3, channels=1) > 0


def test_16bit_pcm_still_works(tmp_path: Path) -> None:
    path = tmp_path / "voice16.wav"
    sample = (1000).to_bytes(2, "little", signed=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(sample * 480)
    rms = _Rms(path, RATE)
    try:
        assert rms(0, 480) > 900
    finally:
        rms.close()


def test_unsupported_pcm_width_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "voice32.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(4)
        handle.setframerate(RATE)
        handle.writeframes(b"\x00" * 16)
    rms = _Rms(path, RATE)
    try:
        with pytest.raises(ValueError, match="Unsupported PCM sample width: 4"):
            rms(0, 4)
    finally:
        rms.close()

    with pytest.raises(ValueError, match="Unsupported PCM sample width: 1"):
        decode_pcm_mono_rms(b"\x00", sampwidth=1, channels=1)
