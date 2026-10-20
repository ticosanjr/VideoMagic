from __future__ import annotations

import sys
import wave
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from videoflow.adapters.faster_whisper import FasterWhisperAdapter
from videoflow.domain.errors import TranscriptionError


def _wav(path: Path, rate: int = 16000) -> Path:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\0\0" * rate)
    return path


def _model(path: Path) -> Path:
    path.mkdir()
    (path / "model.bin").write_bytes(b"model")
    (path / "config.json").write_text("{}", encoding="utf-8")
    return path


class FakeEngine:
    def __init__(self, segments: list[object]) -> None:
        self.segments = segments
        self.seen: dict[str, object] = {}

    def transcribe(self, audio: str, **kwargs: object) -> tuple[list[object], object]:
        self.seen["audio"] = audio
        self.seen.update(kwargs)
        return self.segments, SimpleNamespace(language="en")


def _word(
    word: str,
    start: float,
    end: float,
    probability: float = 0.9,
) -> SimpleNamespace:
    return SimpleNamespace(word=word, start=start, end=end, probability=probability)


def _segment(text: str, words: list[object] | None) -> SimpleNamespace:
    return SimpleNamespace(text=text, words=words)


def _adapter(model: Path, **kwargs: object) -> FasterWhisperAdapter:
    return FasterWhisperAdapter(model=model, **kwargs)  # type: ignore[arg-type]


def test_word_times_are_exact_source_samples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wav = _wav(tmp_path / "source.wav")
    model = _model(tmp_path / "model")
    engine = FakeEngine(
        [
            _segment(
                " Hello there.",
                [
                    _word(" Hello", 0.0, 0.5, 0.8),
                    _word(" there.", 1.0, 1.25, 1.4),
                ],
            ),
            _segment(
                " Next line.",
                [
                    _word(" Next", 0.333333333, 0.333333333, -0.2),
                    _word(" line.", 0.666666667, 0.666666667, 0.5),
                ],
            ),
        ]
    )
    adapter = _adapter(model, language="en")
    monkeypatch.setattr(adapter, "_load_engine", lambda path: engine)

    sentences = adapter.transcribe(wav, 48000)

    assert [sentence.text for sentence in sentences] == ["Hello there.", "Next line."]
    assert sentences[0].start_sample == 0
    assert sentences[0].end_sample == 60000
    assert sentences[0].words[1].start_sample == 48000
    assert sentences[0].words[1].end_sample == 60000
    assert sentences[0].words[1].probability == 1.0
    assert sentences[1].start_sample == 15999
    assert sentences[1].end_sample == 32001
    assert sentences[1].words[0].probability == 0.0
    assert sentences[0].id == 0
    assert sentences[1].id == 1
    assert engine.seen["audio"] == str(wav)
    assert engine.seen["word_timestamps"] is True
    assert engine.seen["vad_filter"] is False
    assert engine.seen["language"] == "en"


def test_full_wav_and_vad_filter_are_passed_to_the_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wav = _wav(tmp_path / "source.wav")
    model = _model(tmp_path / "model")
    engine = FakeEngine([_segment("One.", [_word("One.", 0.0, 1.0)])])
    adapter = _adapter(model, language="auto", vad_filter=True)
    monkeypatch.setattr(adapter, "_load_engine", lambda path: engine)

    adapter.transcribe(wav, 16000)

    assert engine.seen["audio"] == str(wav)
    assert engine.seen["language"] is None
    assert engine.seen["vad_filter"] is True


def test_missing_word_timestamps_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wav = _wav(tmp_path / "source.wav")
    model = _model(tmp_path / "model")
    adapter = _adapter(model)
    monkeypatch.setattr(
        adapter,
        "_load_engine",
        lambda path: FakeEngine([_segment("No words.", None)]),
    )

    with pytest.raises(TranscriptionError, match="no word timestamps"):
        adapter.transcribe(wav, 16000)


def test_empty_transcript_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wav = _wav(tmp_path / "source.wav")
    model = _model(tmp_path / "model")
    adapter = _adapter(model)
    monkeypatch.setattr(adapter, "_load_engine", lambda path: FakeEngine([]))

    with pytest.raises(TranscriptionError, match="empty transcript"):
        adapter.transcribe(wav, 16000)


def test_missing_model_explains_the_expected_path_and_size(tmp_path: Path) -> None:
    wav = _wav(tmp_path / "source.wav")
    missing = tmp_path / "missing-model"
    adapter = _adapter(missing, model_size="small")

    with pytest.raises(TranscriptionError) as caught:
        adapter.transcribe(wav, 16000)
    message = str(caught.value)
    assert str(missing) in message
    assert "484 MB" in message
    assert "VIDEOWFLOW_FASTER_WHISPER_MODEL" in message


def test_requires_16k_audio(tmp_path: Path) -> None:
    wav = _wav(tmp_path / "source.wav", rate=48000)
    model = _model(tmp_path / "model")
    with pytest.raises(TranscriptionError, match="16 kHz"):
        _adapter(model).transcribe(wav, 48000)


def test_cuda_load_failure_is_not_silently_downgraded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wav = _wav(tmp_path / "source.wav")
    model = _model(tmp_path / "model")

    class CudaFailure:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("CUDA driver is missing")

    fake = ModuleType("faster_whisper")
    fake.WhisperModel = CudaFailure  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    adapter = _adapter(model, device="cuda", compute_type="float16")

    with pytest.raises(TranscriptionError, match="CUDA"):
        adapter.transcribe(wav, 16000)


def test_available_requires_package_and_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import videoflow.adapters.faster_whisper as module

    model = _model(tmp_path / "model")
    monkeypatch.setattr(module.importlib.util, "find_spec", lambda name: object())
    assert FasterWhisperAdapter.available(model=model) is True

    monkeypatch.setattr(module.importlib.util, "find_spec", lambda name: None)
    assert FasterWhisperAdapter.available(model=model) is False
