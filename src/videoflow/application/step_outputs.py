"""Persisted per-step outputs for inspection and manual comparison."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

STEP_OUTPUTS_FILE = "outputs.json"


def step_outputs_path(output: Path, step_id: str) -> Path:
    return Path(output) / "work" / "steps" / step_id / STEP_OUTPUTS_FILE


def jsonable(value: Any) -> Any:
    """Turn domain objects and paths into JSON-safe values."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json")
        except TypeError:
            return dump()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    return str(value)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def write_step_outputs(
    output: Path,
    *,
    step_id: str,
    step_type: str,
    status: str,
    fingerprint: str,
    ports: Mapping[str, Any],
    port_specs: Iterable[Any],
    hashes: Mapping[str, str] | None = None,
    files: Iterable[str] = (),
    artifacts: Mapping[str, str] | None = None,
    elapsed_ms: int = 0,
) -> Path:
    entries: list[dict[str, Any]] = []
    for spec in port_specs:
        port_id = str(getattr(spec, "id", ""))
        value = jsonable(ports.get(port_id))
        encoded = json.dumps(value, default=str)
        entries.append(
            {
                "id": port_id,
                "label": str(getattr(spec, "label", port_id)),
                "type": str(getattr(spec, "type", "any")),
                "hash": str((hashes or {}).get(port_id, "")),
                "size_bytes": len(encoded.encode("utf-8")),
                "value": value,
            }
        )
    file_entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in files:
        path = Path(raw).expanduser()
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        file_entries.append(
            {
                "name": path.name,
                "path": key,
                "exists": path.is_file(),
                "size_bytes": path.stat().st_size if path.is_file() else 0,
            }
        )
    artifact_entries = [
        {"name": str(name), "path": str(path)}
        for name, path in (artifacts or {}).items()
    ]
    payload = {
        "schema_version": 1,
        "step_id": step_id,
        "type": step_type,
        "status": status,
        "fingerprint": fingerprint,
        "elapsed_ms": elapsed_ms,
        "ports": entries,
        "files": file_entries,
        "artifacts": artifact_entries,
    }
    path = step_outputs_path(output, step_id)
    _write_json(path, payload)
    return path


def load_step_outputs(output: Path, step_id: str) -> dict[str, Any] | None:
    path = step_outputs_path(output, step_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def summarize_step_outputs(payload: dict[str, Any]) -> dict[str, Any]:
    ports: list[dict[str, Any]] = []
    for item in payload.get("ports", []):
        if not isinstance(item, dict):
            continue
        ports.append(
            {
                "id": str(item.get("id", "")),
                "label": str(item.get("label", item.get("id", ""))),
                "type": str(item.get("type", "any")),
                "hash": str(item.get("hash", "")),
                "size_bytes": int(item.get("size_bytes", 0) or 0),
                "has_value": "value" in item,
            }
        )
    return {
        "step_id": str(payload.get("step_id", "")),
        "type": str(payload.get("type", "")),
        "status": str(payload.get("status", "")),
        "fingerprint": str(payload.get("fingerprint", "")),
        "elapsed_ms": int(payload.get("elapsed_ms", 0) or 0),
        "ports": ports,
        "files": list(payload.get("files", [])),
        "artifacts": list(payload.get("artifacts", [])),
    }


def step_output_port(payload: dict[str, Any], port_id: str) -> dict[str, Any] | None:
    for item in payload.get("ports", []):
        if isinstance(item, dict) and str(item.get("id", "")) == port_id:
            return item
    return None


def save_step_outputs(
    output: Path, step_id: str, target_dir: Path
) -> list[str]:
    payload = load_step_outputs(output, step_id)
    if payload is None:
        return []
    target_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    destination = target_dir / f"{step_id}-outputs.json"
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    saved.append(str(destination))
    for item in payload.get("files", []):
        if not isinstance(item, dict):
            continue
        path = Path(str(item.get("path", ""))).expanduser()
        if not path.is_file():
            continue
        copy = target_dir / path.name
        if copy.exists() and copy.resolve() == path.resolve():
            continue
        shutil.copy2(path, copy)
        saved.append(str(copy))
    return saved
