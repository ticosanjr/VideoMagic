from __future__ import annotations

import json
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from videoflow.adapters.yamnet import SAMPLE_RATE, WINDOW_SAMPLES, YamnetAdapter
from videoflow.application.rms import build_rms_profile
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError
from videoflow.domain.state import MediaInfo
from videoflow.steps.audio import _persist_rms
from videoflow.steps.audio_events import AudioEventsParams, AudioEventsStep
from videoflow.steps.base import StepIO


class FakeSession:
    def __init__(self, rows: list[list[float]]) -> None:
        self.rows = rows
        self.index = 0

    def get_inputs(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(name="input")]

    def run(self, _names: object, inputs: dict[str, object]) -> list[np.ndarray]:
        assert inputs["input"].shape == (1, WINDOW_SAMPLES)  # type: ignore[attr-defined]
        row = self.rows[min(self.index, len(self.rows) - 1)]
        self.index += 1
        return [np.asarray([row], dtype=np.float32)]


def write_wav(path: Path, *, seconds: float = 1.0, amplitude: float = 0.0) -> Path:
    frames = int(seconds * SAMPLE_RATE)
    data = (np.sin(np.arange(frames) * 0.05) * amplitude * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(data.tobytes())
    return path


def adapter_with(tmp_path: Path, rows: list[list[float]]) -> YamnetAdapter:
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"0": "Cough", "1": "Speech", "2": "Sneeze"}), encoding="utf-8")
    adapter = YamnetAdapter(model=tmp_path / "yamnet.onnx", labels=labels)
    adapter._session = FakeSession(rows)  # type: ignore[assignment]
    return adapter


def pcm(seconds: float = 1.0) -> np.ndarray:
    return np.zeros(int(SAMPLE_RATE * seconds), dtype=np.float32)


def test_yamnet_detects_and_merges_a_cough(tmp_path: Path) -> None:
    adapter = adapter_with(tmp_path, [[0.8, 0.1, 0.0], [0.7, 0.1, 0.0], [0.0, 0.1, 0.0]])
    events = adapter.detect(pcm(), sample_rate=SAMPLE_RATE, merge_gap_ms=200)
    assert len(events) == 1
    assert events[0].label == "Cough"
    assert events[0].action == "remove"
    assert events[0].end_sample - events[0].start_sample >= WINDOW_SAMPLES


def test_yamnet_low_threshold_requires_low_asr_confidence(tmp_path: Path) -> None:
    adapter = adapter_with(tmp_path, [[0.35, 0.1, 0.0]])
    low = adapter.detect(
        pcm(),
        sample_rate=SAMPLE_RATE,
        word_spans=[(0, WINDOW_SAMPLES, 0.20)],
        threshold=0.45,
        low_threshold=0.30,
        asr_confidence=0.35,
    )
    high = adapter.detect(
        pcm(),
        sample_rate=SAMPLE_RATE,
        word_spans=[(0, WINDOW_SAMPLES, 0.90)],
        threshold=0.45,
        low_threshold=0.30,
        asr_confidence=0.35,
    )
    assert low
    assert high == []


def test_yamnet_scales_events_to_project_rate(tmp_path: Path) -> None:
    adapter = adapter_with(tmp_path, [[0.9, 0.0, 0.0]])
    events = adapter.detect(np.zeros(48_000, dtype=np.float32), sample_rate=48_000)
    assert events
    assert events[0].end_sample > SAMPLE_RATE


def test_yamnet_requires_a_label_map(tmp_path: Path) -> None:
    adapter = YamnetAdapter(model=tmp_path / "yamnet.onnx", labels=tmp_path / "missing.json")
    adapter._session = FakeSession([[0.9, 0.0, 0.0]])  # type: ignore[assignment]
    with pytest.raises(IngestError, match="labels"):
        adapter.detect(pcm(), sample_rate=SAMPLE_RATE)


def test_yamnet_rejects_invalid_thresholds(tmp_path: Path) -> None:
    adapter = adapter_with(tmp_path, [[0.9, 0.0, 0.0]])
    with pytest.raises(IngestError, match="thresholds"):
        adapter.detect(pcm(), sample_rate=SAMPLE_RATE, threshold=0.2, low_threshold=0.4)


def test_rms_profile_has_reference_hop_and_level(tmp_path: Path) -> None:
    path = write_wav(tmp_path / "tone.wav", amplitude=0.5)
    profile = build_rms_profile(path, sample_rate=SAMPLE_RATE)
    assert profile["frame_ms"] == 10
    assert profile["window_ms"] == 25
    assert profile["count"] == 98
    assert min(profile["db"]) > -20


def test_rms_profile_handles_silence(tmp_path: Path) -> None:
    path = write_wav(tmp_path / "silence.wav", amplitude=0.0)
    profile = build_rms_profile(path, sample_rate=SAMPLE_RATE)
    assert profile["count"] == 98
    assert max(profile["db"]) == -180.0


def test_vad_rms_is_persisted_as_an_artifact(tmp_path: Path) -> None:
    source = write_wav(tmp_path / "source.wav", amplitude=0.4)
    context = PipelineContext(
        source=source,
        output=tmp_path / "out",
        work=tmp_path / "out" / "work",
        exports=tmp_path / "out" / "exports",
        pcm_path=source,
    )
    media = MediaInfo(
        source_path=str(source),
        duration_frames=100,
        fps_num=25,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=SAMPLE_RATE,
    )
    _persist_rms(context, media, StepIO())
    artifact = Path(context.artifacts["vad_rms"])
    assert artifact.is_file()
    assert context.metadata["vad_rms"]["frame_ms"] == 10
    assert context.metadata["vad_rms"]["count"] == 98


def test_audio_events_step_falls_back_to_heuristic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_wav(tmp_path / "source.wav", amplitude=0.4)
    context = PipelineContext(
        source=source,
        output=tmp_path / "out",
        work=tmp_path / "out" / "work",
        exports=tmp_path / "out" / "exports",
        pcm_path=source,
        media=MediaInfo(
            source_path=str(source),
            duration_frames=100,
            fps_num=25,
            fps_den=1,
            width=320,
            height=240,
            audio_sample_rate=SAMPLE_RATE,
        ),
    )
    monkeypatch.setattr(
        "videoflow.steps.audio_events.YamnetAdapter.status",
        lambda _self: {"available": False, "reason": "model_missing"},
    )
    monkeypatch.setattr(
        "videoflow.steps.audio_events.detect_audio_events",
        lambda *_args, **_kwargs: [(0, 160)],
    )
    AudioEventsStep().run(context, AudioEventsParams(), StepIO())
    assert context.metadata["audio_events_report"]["engine"] == "heuristic"
    assert len(context.metadata["audio_events"]) == 1
    assert Path(context.artifacts["audio_events"]).is_file()
