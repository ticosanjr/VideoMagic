"""Persistent artifact and metadata handoff between MCP step jobs.

A step job runs one node in its own :class:`PipelineContext`. Without a small
project-level ledger, a later tool call cannot see the audio track, transcript
plan, or other paths produced by an earlier call. Recipe runs keep their own
in-memory context; this ledger is the bridge for the tools-only MCP surface.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

STATE_FILE = "step-state.json"
_MAX_METADATA_BYTES = 2_000_000


def state_path(output: Path | str) -> Path:
    return Path(output).expanduser() / STATE_FILE


def _read(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _json_safe(value: Any) -> Any:
    try:
        encoded = json.dumps(value, default=str)
    except (TypeError, ValueError):
        return {}
    if len(encoded) > _MAX_METADATA_BYTES:
        return {}
    return json.loads(encoded)


def load_step_state(output: Path | str) -> tuple[dict[str, str], dict[str, Any]]:
    payload = _read(state_path(output))
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    live: dict[str, str] = {}
    for key, value in artifacts.items():
        if not isinstance(value, str) or not value.strip():
            continue
        path = Path(value).expanduser()
        if path.is_file():
            live[str(key)] = str(path)
    return live, dict(metadata)


def save_step_state(
    output: Path | str,
    artifacts: dict[str, Any] | None,
    metadata: dict[str, Any] | None = None,
) -> Path:
    path = state_path(output)
    existing_artifacts, existing_metadata = load_step_state(output)
    merged_artifacts = dict(existing_artifacts)
    for key, value in (artifacts or {}).items():
        if not isinstance(value, str) or not value.strip():
            continue
        candidate = Path(value).expanduser()
        if candidate.is_file():
            merged_artifacts[str(key)] = str(candidate)
    merged_metadata = dict(existing_metadata)
    merged_metadata.update(_json_safe(metadata or {}))
    payload = {"artifacts": merged_artifacts, "metadata": merged_metadata}
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return path


__all__ = ["STATE_FILE", "load_step_state", "save_step_state", "state_path"]
