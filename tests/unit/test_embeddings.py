"""Optional embedding scoring with a deterministic fake model."""

from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application import embedding_worker, embeddings


class FakeModel:
    def encode(self, texts: list[str], normalize_embeddings: bool = True):
        return [[1.0, 0.0] if "city" in text else [0.0, 1.0] for text in texts]


def test_scores_rank_the_matching_document(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    monkeypatch.setenv("VIDEOWFLOW_EMBEDDING_MODEL", str(model_dir))
    monkeypatch.setattr(embeddings, "available", lambda: True)
    monkeypatch.setattr(embedding_worker, "model", lambda _path: FakeModel())

    scores = embeddings.scores("city skyline", ["city skyline", "office desk"])

    assert scores is not None
    assert scores[0] > scores[1]


def test_available_requires_a_local_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("VIDEOWFLOW_EMBEDDING_MODEL", raising=False)
    assert embeddings.available() is False
    monkeypatch.setenv("VIDEOWFLOW_EMBEDDING_MODEL", str(tmp_path / "missing"))
    assert embeddings.available() is False


def test_cosine_handles_zero_vectors() -> None:
    assert embeddings.cosine([], [1.0]) == 0.0
    assert embeddings.cosine([0.0, 0.0], [0.0, 0.0]) == 0.0
