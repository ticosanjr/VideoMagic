"""Waveform peak extraction, normalisation, and range slicing."""

from __future__ import annotations

import wave
from array import array
from pathlib import Path

import pytest

from videoflow.application import waveforms


def write_wav(path: Path, *, sample_rate: int = 4000, blocks: list[tuple[int, int]]) -> Path:
    samples = array("h")
    for amplitude, count in blocks:
        samples.extend([amplitude] * count)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(samples.tobytes())
    return path


def test_compute_peaks_normalises_and_buckets(tmp_path: Path) -> None:
    source = write_wav(tmp_path / "audio.wav", blocks=[(1000, 800), (20000, 800)])

    peaks = waveforms.compute_peaks(source, bucket_samples=400)

    assert len(peaks) == 4
    assert peaks[0] == pytest.approx(0.05, abs=0.001)
    assert peaks[-1] == pytest.approx(1.0, abs=0.001)


def test_compute_peaks_handles_silence(tmp_path: Path) -> None:
    source = write_wav(tmp_path / "silent.wav", blocks=[(0, 800)])

    assert waveforms.compute_peaks(source, bucket_samples=400) == pytest.approx([0.0, 0.0])


def test_peaks_for_range_slices_and_resamples(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    peaks = [round(index / 100, 2) for index in range(40)]
    monkeypatch.setattr(
        waveforms,
        "analyse_source",
        lambda _source, refresh=False: {
            "peaks": peaks,
            "bucket_sec": 0.05,
            "duration_sec": 2.0,
        },
    )

    result = waveforms.peaks_for_range(
        tmp_path / "any.mp4", start_sec=0.5, end_sec=0.9, buckets=4
    )

    assert len(result["peaks"]) == 4
    assert result["start_sec"] == 0.5
    assert result["peaks"] == pytest.approx(
        [max(peaks[10:12]), max(peaks[12:14]), max(peaks[14:16]), max(peaks[16:18])]
    )


def test_cache_reuses_the_same_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    source = write_wav(tmp_path / "audio.wav", blocks=[(500, 400)])
    calls: list[Path] = []

    def fake_extract(self, src, destination, *, sample_rate=16000):
        calls.append(Path(src))
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        write_wav(destination, sample_rate=sample_rate, blocks=[(500, 400)])
        return destination

    monkeypatch.setattr(waveforms.FFmpegAdapter, "extract_pcm", fake_extract)

    first = waveforms.analyse_source(source)
    second = waveforms.analyse_source(source)

    assert first["peaks"] == second["peaks"]
    assert len(calls) == 1
