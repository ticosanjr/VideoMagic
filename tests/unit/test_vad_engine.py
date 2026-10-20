from pathlib import Path

import pytest

from videoflow.application import vad
from videoflow.domain.errors import IngestError
from videoflow.domain.state import MediaInfo


def media(path: Path) -> MediaInfo:
    return MediaInfo(
        source_path=str(path),
        duration_frames=90,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=48000,
    )


class FakeEngine:
    def __init__(self) -> None:
        self.rates: list[int] = []
        self.detect_calls = 0

    def extract_pcm(self, source: Path, destination: Path, *, sample_rate: int) -> Path:
        self.rates.append(sample_rate)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"RIFF")
        return destination

    def detect_speech(self, wav_path: Path, **kwargs: object) -> list[tuple[int, int]]:
        self.detect_calls += 1
        return [(0, 48000)]


def test_rescale_spans_uses_exact_floor_and_ceil() -> None:
    assert vad.rescale_spans([(1, 2)], 16000, 44100) == [(2, 6)]
    assert vad.rescale_spans([(0, 16000), (16001, 32000)], 16000, 48000) == [
        (0, 48000),
        (48003, 96000),
    ]
    assert vad.rescale_spans([(0, 16000)], 16000, 48000, duration_samples=1000) == [(0, 1000)]


def test_pad_spans_clamps_and_merges() -> None:
    assert vad.pad_spans([(48000, 96000)], 48000, 120, 150) == [(42240, 103200)]
    assert vad.pad_spans(
        [(48000, 96000), (96050, 100000)], 48000, 120, 150, duration_samples=100000
    ) == [(42240, 100000)]
    with pytest.raises(IngestError):
        vad.pad_spans([], 48000, -1, 0)


def test_auto_falls_back_to_ffmpeg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vad.SileroVadAdapter, "available", staticmethod(lambda: False))
    engine = FakeEngine()
    source = tmp_path / "source.mp4"
    result = vad.detect_speech(engine, source, tmp_path / "work", media(source))
    assert result.engine == "ffmpeg"
    assert result.spans == [(0, 55200)]
    assert engine.detect_calls == 1
    assert engine.rates == []


def test_auto_uses_silero_and_rescales(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeSilero:
        @staticmethod
        def available() -> bool:
            return True

        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def detect(self, wav_path: Path) -> list[tuple[int, int]]:
            assert wav_path.name == "vad.wav"
            return [(0, 16000), (32000, 48000)]

    monkeypatch.setattr(vad, "SileroVadAdapter", FakeSilero)
    engine = FakeEngine()
    source = tmp_path / "source.mp4"
    result = vad.detect_speech(
        engine,
        source,
        tmp_path / "work",
        media(source),
        speech_pad_before_ms=0,
        speech_pad_after_ms=0,
    )
    assert result.engine == "silero"
    assert result.spans == [(0, 48000), (96000, 144000)]
    assert engine.rates == [16000]


def test_explicit_silero_fails_with_an_actionable_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(vad.SileroVadAdapter, "available", staticmethod(lambda: False))
    source = tmp_path / "source.mp4"
    with pytest.raises(IngestError, match="Silero VAD"):
        vad.detect_speech(
            FakeEngine(),
            source,
            tmp_path / "work",
            media(source),
            vad_engine="silero",
        )
