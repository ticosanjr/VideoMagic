"""Content-addressed module hashes.

The hash does not accept a modification time. Mtime is a cache hint for the
runner, never an identity. Float parameters are quantized to 6 decimal places
so binary noise does not bust the cache, and so ``1.15`` is stable.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from decimal import ROUND_HALF_EVEN, Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel

_QUANTUM = Decimal("0.000001")


def canonicalize(value: Any) -> Any:
    """Return a JSON-ready value whose encoding does not depend on key order."""

    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return _canonicalize_float(value)
    if isinstance(value, Decimal):
        return _quantize(value)
    if isinstance(value, Enum):
        return canonicalize(value.value)
    if isinstance(value, Mapping):
        keys = list(value.keys())
        if not all(isinstance(key, str) for key in keys):
            raise TypeError("cache payload keys must be strings")
        return {key: canonicalize(value[key]) for key in sorted(keys)}
    if isinstance(value, (list, tuple)):
        return [canonicalize(item) for item in value]
    raise TypeError(f"cannot canonicalize {type(value).__name__}")


def module_hash(
    *,
    module: str,
    module_version: str,
    enabled: bool,
    params: Mapping[str, Any],
    upstream_hash: str,
    media_fingerprint: str,
    model_artifact_digest: str = "none",
    prompt_template_version: str = "none",
) -> str:
    """SHA-256 of the canonical module identity. Hex digest, lowercase."""

    payload = {
        "enabled": enabled,
        "media_fingerprint": media_fingerprint,
        "model_artifact_digest": model_artifact_digest,
        "module": module,
        "module_version": module_version,
        "params": dict(params),
        "prompt_template_version": prompt_template_version,
        "upstream_hash": upstream_hash,
    }
    encoded = json.dumps(
        canonicalize(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def params_from_model(model: BaseModel) -> dict[str, Any]:
    """Dump a config model into the mapping ``module_hash`` expects."""

    dumped: dict[str, Any] = model.model_dump(mode="json")
    return dumped


def _canonicalize_float(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("non-finite float cannot enter a cache hash")
    return _quantize(Decimal(str(value)))


def _quantize(value: Decimal) -> str:
    quantized = value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)
    if quantized == 0:
        return "0.000000"
    return format(quantized, "f")
