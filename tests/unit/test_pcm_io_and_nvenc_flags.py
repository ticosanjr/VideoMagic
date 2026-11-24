"""PCM 24/32-bit safety, NVENC flags, overlays, and audio source selection."""

from __future__ import annotations

import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from videoflow.application.master_export import resolve_audio_master
from videoflow.application.overlay_geometry import overlay_box
from videoflow.core import nvenc
from videoflow.domain.state import OverlayClip
from videoflow.domains.audio import finalize
from videoflow.domains.audio.pcm_io import decode_pcm_mono_rms, read_wav_mono_float32
from videoflow.steps.audio_finalize import AudioFinalizeParams

RATE = 48_000


def _write(path: Path, samples: bytes, *, width: int, channels: int = 1) -> Path:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(width)
        handle.setframerate(RATE)
        handle.writeframes(samples)
    return path


def test_24bit_reader_ignores_an_incomplete_trailing_frame(tmp_path: Path) -> None:
    sample = (1000 << 8).to_bytes(3, "little", signed=True)
    path = _write(tmp_path / "voice24.wav", sample * 480 + b"\x7f", width=3)
    samples, rate = read_wav_mono_float32(path)
    assert rate == RATE
    assert samples.size == 480
    assert np.max(np.abs(samples)) > 0.01


def test_24bit_stereo_is_downmixed(tmp_path: Path) -> None:
    left = (1000 << 8).to_bytes(3, "little", signed=True)
    right = (-1000 << 8).to_bytes(3, "little", signed=True)
    path = _write(tmp_path / "stereo24.wav", (left + right) * 64, width=3, channels=2)
    samples, _rate = read_wav_mono_float32(path)
    assert samples.size == 64
    assert np.max(np.abs(samples)) < 0.001


def test_32bit_reader_and_rms_helper(tmp_path: Path) -> None:
    sample = (1000 << 16).to_bytes(4, "little", signed=True)
    path = _write(tmp_path / "voice32.wav", sample * 480, width=4)
    samples, _rate = read_wav_mono_float32(path)
    assert samples.size == 480
    assert np.max(np.abs(samples)) > 0.01
    assert decode_pcm_mono_rms(sample * 2 + b"\xff", sampwidth=4, channels=1) > 0


def test_unsupported_width_still_fails_closed(tmp_path: Path) -> None:
    path = _write(tmp_path / "voice8.wav", b"\x00" * 32, width=1)
    with pytest.raises(ValueError, match="Unsupported PCM sample width: 1"):
        read_wav_mono_float32(path)


def test_nvenc_candidates_try_hyphenated_aq_before_the_universal_profile() -> None:
    first, second = nvenc.CANDIDATES[:2]
    assert "-spatial-aq" in first
    assert first[first.index("-spatial-aq") + 1] == "1"
    assert "-spatial-aq" not in second
    assert second == nvenc.DEFAULT_ARGS


def test_fullscreen_overlay_uses_the_whole_canvas() -> None:
    overlay = OverlayClip(
        overlay_id="full",
        path="/tmp/missing.png",
        start_frame=0,
        duration_frames=30,
        anchor="fullscreen",
        width_ratio=0.2,
    )
    box = overlay_box(overlay, 1920, 1080)
    assert (box.x, box.y, box.width, box.height) == (0, 0, 1920, 1080)


def test_audio_source_prefers_final_mix_and_accepts_an_explicit_path(
    tmp_path: Path,
) -> None:
    (tmp_path / "audio").mkdir()
    mix = tmp_path / "audio" / "final_mix.wav"
    mix.write_bytes(b"mix")
    explicit = tmp_path / "custom.wav"
    explicit.write_bytes(b"custom")
    assert resolve_audio_master(tmp_path, "mix") == mix
    assert resolve_audio_master(tmp_path, "final") == mix
    assert resolve_audio_master(tmp_path, str(explicit)) == explicit
    assert resolve_audio_master(tmp_path, "timeline") is None


def test_audio_finalize_params_expose_ducking_and_music_db() -> None:
    params = AudioFinalizeParams()
    assert params.ducking is True
    assert params.music_gain_db == -18.0


def test_loudnorm_parser_reads_json_from_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = (
        'noise {"input_i":"-16.0","input_tp":"-2.0",'
        '"input_lra":"7.0","input_thresh":"-26.0"} tail'
    )
    monkeypatch.setattr(finalize, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        finalize.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=payload, stderr=""),
    )
    measured = finalize._measure_loudnorm(
        "[0:a]anull[mix]",
        ["-i", "voice.wav"],
        target_lufs=-16.0,
        true_peak_db=-2.0,
    )
    assert measured["input_i"] == -16.0
    assert measured["input_thresh"] == -26.0


def test_ducking_false_removes_the_sidechain_compressor() -> None:
    graph = finalize._build_graph(
        duration=1.0,
        mono_repair="",
        music=True,
        sfx=False,
        music_gain=0.2,
        sfx_gain=0.5,
        ducking=False,
    )
    assert "sidechaincompress" not in graph
    assert "amix=inputs=2" in graph
