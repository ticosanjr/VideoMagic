from __future__ import annotations

import struct
import wave
from pathlib import Path

from videoflow.application.silence import cap_silence_spans, detect_silence_spans


def _write_wav(path: Path, samples: list[int], rate: int = 1_000) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(struct.pack("<h", value) for value in samples))


def test_detect_silence_spans_uses_threshold_and_minimum(tmp_path: Path) -> None:
    path = tmp_path / "audio.wav"
    _write_wav(path, [1_000] * 500 + [0] * 500 + [1_000] * 500, rate=1_000)
    spans = detect_silence_spans(
        path,
        sample_rate=1_000,
        frame_ms=10,
        threshold_db=-35.0,
        min_ms=100,
    )
    assert spans == [(500, 1_000)]


def test_cap_silence_keeps_short_pauses_and_caps_long_ones() -> None:
    spans, removed = cap_silence_spans(
        [(0, 10_000)],
        [(2_000, 7_000)],
        sample_rate=1_000,
        max_silence_ms=500,
        keep_silence_ms=300,
        pad_before_ms=20,
        pad_after_ms=40,
        min_clip_ms=10,
    )
    assert spans == [(0, 2_150), (6_850, 10_000)]
    assert removed == 4.7


def test_cap_silence_trims_edges_and_keeps_short_gap() -> None:
    leading, _ = cap_silence_spans(
        [(0, 10_000)],
        [(0, 3_000)],
        sample_rate=1_000,
        max_silence_ms=500,
        keep_silence_ms=300,
        pad_before_ms=20,
        pad_after_ms=40,
    )
    trailing, _ = cap_silence_spans(
        [(0, 10_000)],
        [(7_000, 10_000)],
        sample_rate=1_000,
        max_silence_ms=500,
        keep_silence_ms=300,
        pad_before_ms=20,
        pad_after_ms=40,
    )
    short, _ = cap_silence_spans(
        [(0, 10_000)],
        [(2_000, 2_500)],
        sample_rate=1_000,
        max_silence_ms=500,
        keep_silence_ms=300,
    )
    assert leading == [(2_980, 10_000)]
    assert trailing == [(0, 7_040)]
    assert short == [(0, 10_000)]


def test_cap_silence_removes_a_span_that_is_all_silence() -> None:
    spans, _ = cap_silence_spans(
        [(0, 5_000)],
        [(0, 5_000)],
        sample_rate=1_000,
        max_silence_ms=500,
        keep_silence_ms=300,
    )
    assert spans == []


def test_detect_silence_scales_to_the_requested_rate(tmp_path: Path) -> None:
    path = tmp_path / "audio.wav"
    _write_wav(path, [1_000] * 500 + [0] * 500, rate=1_000)
    spans = detect_silence_spans(path, sample_rate=500, frame_ms=10, min_ms=100)
    assert spans == [(250, 500)]


def test_cap_silence_drops_a_too_short_piece() -> None:
    spans, removed = cap_silence_spans(
        [(0, 100)],
        [(40, 90)],
        sample_rate=1_000,
        max_silence_ms=10,
        keep_silence_ms=0,
        pad_before_ms=20,
        pad_after_ms=20,
        min_clip_ms=100,
    )
    assert spans == []
    assert removed > 0
