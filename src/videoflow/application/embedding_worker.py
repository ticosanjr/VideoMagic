"""Lazy sentence-transformers loader shared by the embedding helpers."""

from __future__ import annotations

from typing import Any

_MODEL: Any = None
_MODEL_PATH = ""


def model(path: str) -> Any:
    global _MODEL, _MODEL_PATH
    if _MODEL is not None and path == _MODEL_PATH:
        return _MODEL
    try:
        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer(path)
        _MODEL_PATH = path
    except Exception:
        _MODEL = None
    return _MODEL
