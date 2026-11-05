from __future__ import annotations

from pathlib import Path

import numpy as np

from videoflow.application.non_speech import (
    detect_impulsive_noise,
    load_pcm_mono,
)


def _base() -> np.ndarray:
    rate = 1000
    signal = np.zeros(1500, dtype=np.float32)
    time = np.arange(300, dtype=np.float32) / rate
    signal[0:300] = 0.2 * np.sin(2 * np.pi * 200 * time)
    signal[800:1100] = 0.2 * np.sin(2 * np.pi * 200 * time)
    return signal


def test_isolated_broadband_burst_is_detected() -> None:
    signal = _base()
    rng = np.random.default_rng(1)
    signal[400:600] = 0.5 * rng.normal(size=200).astype(np.float32)
    spans = detect_impulsive_noise(
        signal,
        [(0, 300), (800, 1100)],
        sample_rate=1000,
        rms_threshold=0.02,
    )
    assert spans
    assert any(350 <= start <= 450 and 550 <= end <= 650 for start, end in spans)


def test_burst_inside_a_word_is_protected() -> None:
    signal = _base()
    rng = np.random.default_rng(2)
    signal[100:250] = 0.5 * rng.normal(size=150).astype(np.float32)
    spans = detect_impulsive_noise(
        signal,
        [(0, 300), (800, 1100)],
        sample_rate=1000,
        rms_threshold=0.02,
    )
    assert not any(start < 300 and end > 0 for start, end in spans)


def test_low_energy_burst_is_ignored() -> None:
    signal = _base()
    rng = np.random.default_rng(3)
    signal[400:600] = 0.001 * rng.normal(size=200).astype(np.float32)
    spans = detect_impulsive_noise(
        signal,
        [(0, 300), (800, 1100)],
        sample_rate=1000,
        rms_threshold=0.02,
    )
    assert spans == []


def test_missing_pcm_returns_empty() -> None:
    assert load_pcm_mono(Path("/tmp/definitely-missing.wav")).size == 0


def _write_wav(
    path: Path,
    samples: np.ndarray,
    *,
    rate: int,
    channels: int = 1,
    width: int = 2,
) -> None:
    import struct
    import wave

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(width)
        handle.setframerate(rate)
        if width == 2:
            handle.writeframes(
                b"".join(struct.pack("<h", int(value)) for value in samples)
            )
        else:
            handle.writeframes(bytes(int(value) & 0xFF for value in samples))


def test_load_pcm_mono_downmixes_and_resamples(tmp_path: Path) -> None:
    path = tmp_path / "stereo-8k.wav"
    rate = 8000
    time = np.arange(rate, dtype=np.float32) / rate
    mono = (0.2 * np.sin(2 * np.pi * 220 * time) * 32767).astype(np.int16)
    stereo = np.column_stack([mono, mono]).reshape(-1)
    _write_wav(path, stereo, rate=rate, channels=2)
    pcm = load_pcm_mono(path, sample_rate=16_000)
    assert pcm.size >= 15_900
    assert pcm.size <= 16_100


def test_load_pcm_mono_rejects_non_16bit(tmp_path: Path) -> None:
    path = tmp_path / "8bit.wav"
    _write_wav(path, np.arange(100), rate=8000, width=1)
    assert load_pcm_mono(path).size == 0
