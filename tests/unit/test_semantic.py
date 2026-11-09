from __future__ import annotations

from pathlib import Path

import numpy as np

from videoflow.application import semantic


def test_model_path_uses_env(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("VIDEOFLOW_EMBEDDING_MODEL", str(tmp_path))
    assert semantic.model_path() == tmp_path
    assert semantic.available() is True


def test_model_path_rejects_missing_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOFLOW_EMBEDDING_MODEL", str(tmp_path / "missing"))
    assert semantic.model_path() is None
    assert semantic.available() is False


def test_cosine_handles_vectors() -> None:
    assert semantic.cosine(np.array([1.0, 0.0]), np.array([1.0, 0.0])) == 1.0
    assert semantic.cosine(np.array([1.0, 0.0]), np.array([0.0, 1.0])) == 0.0


def test_encode_returns_none_without_model(monkeypatch) -> None:
    monkeypatch.setenv("VIDEOFLOW_EMBEDDING_MODEL", "/tmp/does-not-exist")
    assert semantic.encode(["a", "b"]) is None


def test_encode_uses_loaded_model(monkeypatch) -> None:
    class Model:
        def encode(self, texts, **kwargs):
            return np.ones((len(texts), 3), dtype=np.float32)

    monkeypatch.setattr(semantic, "_load", lambda: Model())
    vectors = semantic.encode(["a", "b"])
    assert vectors is not None
    assert vectors.shape == (2, 3)


def test_encode_empty_returns_empty_matrix(monkeypatch) -> None:
    monkeypatch.setattr(semantic, "_load", lambda: None)
    vectors = semantic.encode([])
    assert vectors is not None
    assert vectors.shape == (0, 0)
