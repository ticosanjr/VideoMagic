import wave
from pathlib import Path

import numpy as np
import pytest

from videoflow.adapters.silero import SAMPLE_RATE, WINDOW_SAMPLES, SileroVadAdapter
from videoflow.domain.errors import IngestError


class FakeSession:
    def __init__(self, probabilities: list[float]) -> None:
        self.probabilities = probabilities
        self.index = 0

    def run(self, output_names: list[str], inputs: dict[str, object]) -> tuple[object, object]:
        assert output_names == ["output", "stateN"]
        assert inputs["input"].shape[1] == WINDOW_SAMPLES  # type: ignore[attr-defined]
        probability = self.probabilities[self.index]
        self.index += 1
        return np.array([[probability]], dtype=np.float32), inputs["state"]


def write_wav(path: Path, *, seconds: float = 1.0, sample_rate: int = SAMPLE_RATE) -> Path:
    frames = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * frames)
    return path


def adapter_with(
    monkeypatch: pytest.MonkeyPatch, probabilities: list[float], **kwargs: object
) -> SileroVadAdapter:
    adapter = SileroVadAdapter(model=Path("fake.onnx"), **kwargs)
    monkeypatch.setattr(adapter, "_load_session", lambda: FakeSession(probabilities))
    return adapter


def test_silero_merges_short_gaps_and_filters_short_speech(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    probabilities = [0.0] * 32
    for index in list(range(5, 10)) + list(range(12, 16)):
        probabilities[index] = 0.9
    adapter = adapter_with(
        monkeypatch,
        probabilities,
        min_silence_ms=100,
        min_speech_ms=100,
    )
    spans = adapter.detect(write_wav(tmp_path / "audio.wav"))
    assert spans == [(5 * WINDOW_SAMPLES, 16 * WINDOW_SAMPLES)]


def test_silero_keeps_contiguous_windows_without_a_silence_gap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    probabilities = [0.0] * 32
    for index in (5, 6, 7):
        probabilities[index] = 0.9
    adapter = adapter_with(monkeypatch, probabilities, min_silence_ms=0, min_speech_ms=0)
    assert adapter.detect(write_wav(tmp_path / "audio.wav")) == [
        (5 * WINDOW_SAMPLES, 8 * WINDOW_SAMPLES)
    ]


def test_silero_returns_no_spans_below_threshold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    adapter = adapter_with(monkeypatch, [0.2] * 32)
    assert adapter.detect(write_wav(tmp_path / "audio.wav")) == []


def test_silero_requires_16khz_mono_pcm(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="16000"):
        SileroVadAdapter(model=tmp_path / "missing.onnx").detect(
            write_wav(tmp_path / "audio.wav", sample_rate=8000)
        )


def test_silero_reports_a_missing_model(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="model was not found"):
        SileroVadAdapter(model=tmp_path / "missing.onnx").detect(write_wav(tmp_path / "audio.wav"))
