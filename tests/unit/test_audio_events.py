from __future__ import annotations

from pathlib import Path

import numpy as np

from videoflow.domains.audio.events import (
    FEATURE_NAMES,
    EventModel,
    default_model_path,
    detect_audio_events,
    load_model,
    save_model,
    score_candidates,
    span_features,
    train_model,
)


def _pcm(rate: int = 8000, seconds: float = 1.0) -> np.ndarray:
    time = np.arange(int(rate * seconds), dtype=np.float32) / rate
    return (0.2 * np.sin(2 * np.pi * 220 * time)).astype(np.float32)


def test_span_features_has_expected_shape() -> None:
    features = span_features(_pcm(), 0, 800, sample_rate=8000)
    assert features is not None
    assert features.shape == (len(FEATURE_NAMES),)


def test_span_features_rejects_tiny_span() -> None:
    assert span_features(_pcm(), 0, 2, sample_rate=8000) is None


def test_train_save_load_and_score(tmp_path: Path) -> None:
    rng = np.random.default_rng(3)
    features = rng.normal(size=(12, len(FEATURE_NAMES)))
    labels = np.array([1, 0] * 6)
    model = train_model(features, labels, epochs=50)
    path = save_model(model, tmp_path / "model.json")
    loaded = load_model(path)
    assert loaded is not None
    assert 0.0 <= loaded.score(features[0]) <= 1.0


def test_load_model_rejects_low_quality(tmp_path: Path) -> None:
    model = EventModel(
        feature_names=FEATURE_NAMES,
        mean=np.zeros(len(FEATURE_NAMES)),
        scale=np.ones(len(FEATURE_NAMES)),
        weights=np.zeros(len(FEATURE_NAMES)),
        bias=0.0,
        metrics={"precision": 0.1, "recall": 0.1},
    )
    path = save_model(model, tmp_path / "bad.json")
    assert load_model(path) is None


def test_detect_audio_events_falls_back_to_heuristic() -> None:
    pcm = _pcm()
    assert detect_audio_events(pcm, [], sample_rate=8000) == []


def test_score_candidates_uses_model_threshold() -> None:
    features = np.zeros(len(FEATURE_NAMES))
    model = EventModel(
        feature_names=FEATURE_NAMES,
        mean=features,
        scale=np.ones(len(FEATURE_NAMES)),
        weights=np.zeros(len(FEATURE_NAMES)),
        bias=10.0,
    )
    assert score_candidates(_pcm(), [(0, 800)], model, sample_rate=8000) == [(0, 800)]


def test_default_model_path_is_under_videoflow_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOFLOW_HOME", str(tmp_path))
    assert default_model_path() == tmp_path / "models" / "audio-events" / "model.json"


def test_score_ast_candidates_uses_noise_labels(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    from videoflow.domains.audio import events_ast as audio_events

    class Tensor:
        def __init__(self, values):
            self.values = values

        def numpy(self):
            return self.values

    class Torch:
        @staticmethod
        def no_grad():
            from contextlib import nullcontext

            return nullcontext()

        @staticmethod
        def sigmoid(logits):
            return Tensor(np.array(logits.values, dtype=float))

    class Extractor:
        def __call__(self, clips, sampling_rate, return_tensors):
            return {"n": len(clips)}

    class Model:
        def __call__(self, n, **inputs):
            return SimpleNamespace(logits=Tensor([[10.0, -10.0]] * n))

    monkeypatch.setitem(sys.modules, "torch", Torch)
    monkeypatch.setattr(audio_events, "_load_ast", lambda: (Extractor(), Model(), [0]))
    kept = audio_events.score_ast_candidates(_pcm(), [(0, 800)], sample_rate=8000, threshold=0.5)
    assert kept == [(0, 800)]


def test_load_ast_from_local_model(monkeypatch, tmp_path) -> None:
    import sys
    from types import SimpleNamespace

    from videoflow.domains.audio import events_ast as audio_events

    model_dir = tmp_path / "ast"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("VIDEOFLOW_AUDIO_TAGGER", str(model_dir))
    monkeypatch.setattr(audio_events, "_AST", None)
    monkeypatch.setattr(audio_events, "_AST_PATH", None)

    class Extractor:
        @staticmethod
        def from_pretrained(path):
            return Extractor()

    class Model:
        config = SimpleNamespace(id2label={0: "Cough", 1: "Speech"})

        @staticmethod
        def from_pretrained(path):
            return Model()

        def eval(self):
            return self

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            ASTFeatureExtractor=Extractor,
            ASTForAudioClassification=Model,
        ),
    )
    loaded = audio_events._load_ast()
    assert loaded is not None
    assert loaded[2] == [0]
    assert audio_events._load_ast() is loaded


def test_resample_preserves_length() -> None:
    from videoflow.domains.audio.events_ast import _resample

    assert _resample(np.ones(8000, dtype=np.float32), 8000, 16000).size == 16000
