"""Optional multilingual sentence embeddings for semantic take matching.

The model is loaded lazily from a local directory; no network access happens at
runtime. When the model or ``sentence-transformers`` is missing, callers fall
back to lexical matching.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

_MODEL: object | None = None
_MODEL_PATH: Path | None = None


def model_path() -> Path | None:
    raw = os.environ.get("VIDEOFLOW_EMBEDDING_MODEL", "").strip()
    if raw:
        path = Path(raw).expanduser()
        return path if (path / "config.json").is_file() else None
    default = (
        Path.home()
        / ".videoflow"
        / "models"
        / "embeddings"
        / "paraphrase-multilingual-MiniLM-L12-v2"
    )
    return default if (default / "config.json").is_file() else None


def available() -> bool:
    if model_path() is None:
        return False
    try:
        import sentence_transformers  # noqa: F401
    except Exception:
        return False
    return True


def _load() -> object | None:
    global _MODEL, _MODEL_PATH
    path = model_path()
    if path is None:
        return None
    if _MODEL is not None and path == _MODEL_PATH:
        return _MODEL
    try:
        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer(str(path))
        _MODEL_PATH = path
        return _MODEL
    except Exception:
        _MODEL = None
        _MODEL_PATH = None
        return None


def encode(texts: list[str]) -> np.ndarray | None:
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    model = _load()
    if model is None:
        return None
    try:
        vectors = model.encode(  # type: ignore[attr-defined]
            texts,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
        )
    except Exception:
        return None
    return np.asarray(vectors, dtype=np.float32)


def cosine(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.clip(np.dot(left, right), -1.0, 1.0))
