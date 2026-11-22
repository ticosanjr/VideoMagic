"""Payloads, input checks and remote materialization shared by media tools."""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import storage
from .errors import (
    InputNotFoundError,
    InvalidArgumentError,
    MissingCommandError,
    OutputNotProducedError,
    RemoteResultError,
)


def _materialize_remote(
    *,
    project_id: str,
    relative_path: str,
    result: Any,
    capability: str,
    cache_key: str,
    kind: str,
) -> storage.AssetRecord:
    metadata: dict[str, Any] = {"capability": capability, "mode": "remote"}
    if isinstance(result, dict) and isinstance(result.get("metadata"), dict):
        metadata.update(result["metadata"])

    data: bytes | None = None
    if isinstance(result, dict) and result.get("data") is not None:
        raw = result["data"]
        data = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
    elif isinstance(result, (bytes, bytearray)):
        data = bytes(result)

    if data is not None:
        return storage.write_output(
            project_id,
            relative_path,
            data=data,
            kind=kind,
            license="generated",
            source=f"remote:{capability}",
            cache_key=cache_key,
            metadata=metadata,
            ai_generated=True,
        )

    source = _path_from_value(result)
    if source is None or not source.is_file():
        raise RemoteResultError(
            f"remote {capability!r} result has no readable file",
            details={"capability": capability, "result_type": type(result).__name__},
        )
    return storage.write_output(
        project_id,
        relative_path,
        source_path=source,
        kind=kind,
        license="generated",
        source=f"remote:{capability}",
        cache_key=cache_key,
        metadata=metadata,
        ai_generated=True,
    )


def _path_from_value(value: Any) -> Path | None:
    if isinstance(value, (str, Path)):
        return Path(str(value)).expanduser()
    if isinstance(value, dict):
        for key in ("path", "output", "asset_path", "file"):
            if value.get(key):
                return Path(str(value[key])).expanduser()
        return None
    for attribute in ("path", "output", "file"):
        raw = getattr(value, attribute, None)
        if raw:
            return Path(str(raw)).expanduser()
    return None


def _payload(
    tool: str,
    project_id: str,
    record: storage.AssetRecord,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "tool": tool,
        "project_id": project_id,
        "output": str(record.path),
        "relative_path": record.relative_path,
        "cache_key": record.cache_key,
        "cached": record.cached,
        "sidecar": str(record.sidecar),
        "license": record.license,
        "source": record.source,
        "sha256": record.sha256,
    }
    payload.update(extra)
    return payload


def _assets_payload(
    tool: str,
    project_id: str,
    records: Sequence[storage.AssetRecord],
    *,
    mode: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "tool": tool,
        "project_id": project_id,
        "mode": mode,
        "cached": all(record.cached for record in records),
        "assets": [_payload(tool, project_id, record, mode=mode) for record in records],
    }


def _ensure_input(value: str | Path | None, argument: str) -> Path:
    if value is None or str(value) == "":
        raise InvalidArgumentError(f"{argument} is required", details={"argument": argument})
    resolved = Path(value).expanduser()
    if not resolved.is_file():
        raise InputNotFoundError(
            f"{argument} not found: {resolved}",
            details={"argument": argument, "path": str(resolved)},
        )
    return resolved


def _require_output(path: Path) -> None:
    if not path.is_file():
        raise OutputNotProducedError(
            f"command did not produce {path}",
            details={"path": str(path)},
        )


def _slug(value: str, *, limit: int = 40) -> str:
    cleaned = "".join(character if character.isalnum() else "_" for character in value.lower())
    collapsed = "_".join(part for part in cleaned.split("_") if part)
    return (collapsed or "asset")[:limit]


def _ffmpeg() -> str:
    configured = os.environ.get("VF_FFMPEG")
    if configured:
        return configured
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise MissingCommandError(
        "ffmpeg is required for this tool; install it or set VF_FFMPEG",
        details={"env": ["VF_FFMPEG"], "executable": "ffmpeg"},
    )


def _output_name(value: str, default: str) -> str:
    raw = value.strip() if value else default
    name = Path(raw).name
    if name in {"", ".", ".."}:
        raise InvalidArgumentError(f"invalid output name: {value!r}")
    return name
