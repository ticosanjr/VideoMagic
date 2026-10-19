from pathlib import Path

import pytest

from videoflow.adapters.ffmpeg import FFmpegAdapter, parse_silence
from videoflow.domain.errors import IngestError

STDERR = """
[silencedetect @ 0x1] silence_start: 1.0
[silencedetect @ 0x1] silence_end: 2.0 | silence_duration: 1.0
[silencedetect @ 0x1] silence_start: 3.0
[silencedetect @ 0x1] silence_end: 4.0 | silence_duration: 1.0
"""


def test_parse_silence_returns_sample_spans() -> None:
    assert parse_silence(STDERR, 6 * 48000, 48000) == [
        (48000, 96000),
        (144000, 192000),
    ]


def test_missing_end_runs_to_the_media_end() -> None:
    assert parse_silence("silence_start: 5.0", 6 * 48000, 48000) == [(240000, 288000)]


def test_overlapping_and_negative_silence_is_normalised() -> None:
    stderr = "silence_start: -0.1\nsilence_end: 0.5\nsilence_start: 0.4\nsilence_end: 1.0"
    assert parse_silence(stderr, 48000, 48000) == [(0, 48000)]


def test_detect_speech_complements_silence(tmp_path: Path, monkeypatch) -> None:
    wav = tmp_path / "source.wav"
    wav.write_bytes(b"x")
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_capture", lambda _args: ("", STDERR))
    spans = adapter.detect_speech(wav, duration_samples=6 * 48000, sample_rate=48000)
    assert spans == [(0, 48000), (96000, 144000), (192000, 288000)]


def test_detect_speech_requires_audio(tmp_path: Path) -> None:
    with pytest.raises(IngestError):
        FFmpegAdapter().detect_speech(
            tmp_path / "missing.wav", duration_samples=48000, sample_rate=48000
        )


def test_short_speech_blips_are_filtered(tmp_path: Path, monkeypatch) -> None:
    wav = tmp_path / "source.wav"
    wav.write_bytes(b"x")
    stderr = "silence_start: 0.0\nsilence_end: 1.0\nsilence_start: 1.002\nsilence_end: 2.0"
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_capture", lambda _args: ("", stderr))
    spans = adapter.detect_speech(
        wav, duration_samples=2 * 48000, sample_rate=48000, min_speech_ms=100
    )
    assert spans == []


def test_detect_speech_requires_positive_duration(tmp_path: Path) -> None:
    wav = tmp_path / "source.wav"
    wav.write_bytes(b"x")
    with pytest.raises(IngestError):
        FFmpegAdapter().detect_speech(wav, duration_samples=0, sample_rate=48000)
