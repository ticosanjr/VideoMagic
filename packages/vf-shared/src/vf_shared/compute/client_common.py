"""Errors and filesystem helpers shared by the GPU worker client."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]{1,200}$")
TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled", "canceled", "done", "error"})


class GPUWorkerError(RuntimeError):
    """Raised when a GPU worker request fails or returns an invalid payload."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GPUWorkerUnsupported(GPUWorkerError):
    """Raised when the worker does not implement an optional transport endpoint."""


def _safe_segment(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or not _SEGMENT_RE.fullmatch(value)
        or value in {".", ".."}
    ):
        raise ValueError(f"invalid {field}: {value!r}")
    return value


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise GPUWorkerError("worker returned invalid JSON") from exc
    if not isinstance(payload, Mapping):
        raise GPUWorkerError("worker returned a non-object JSON payload")
    return {str(key): value for key, value in payload.items()}


def _atomic_write(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()
