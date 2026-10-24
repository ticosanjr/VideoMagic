"""Optional local embedding matching for B-roll.

No model is downloaded implicitly. Set ``VIDEOWFLOW_EMBEDDING_MODEL`` to a local
sentence-transformers directory and install the extra for semantic matching;
otherwise callers keep the TF-IDF fallback.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

from videoflow.application import embedding_worker


def model_path() -> Path | None:
    raw = os.environ.get("VIDEOWFLOW_EMBEDDING_MODEL", "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def available() -> bool:
    if model_path() is None:
        return False
    try:
        import sentence_transformers  # noqa: F401
    except Exception:
        return False
    return True


def encode(texts: list[str]) -> list[list[float]] | None:
    path = model_path()
    if path is None or not texts:
        return None
    model = embedding_worker.model(str(path))
    if model is None:
        return None
    return [list(vector) for vector in model.encode(texts, normalize_embeddings=True)]


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
    right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
    return dot / (left_norm * right_norm)


def scores(query: str, documents: list[str]) -> list[float] | None:
    vectors = encode([query, *documents])
    if not vectors:
        return None
    query_vector, *document_vectors = vectors
    return [cosine(query_vector, vector) for vector in document_vectors]
