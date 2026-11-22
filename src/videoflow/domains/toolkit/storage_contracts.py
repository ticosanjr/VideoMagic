"""Bridge to the shared asset contracts and sidecar writer."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

_KIND_ALIASES = {
    "audio": "voice",
    "matte": "images",
    "upscaled": "images",
    "graphic": "graphics",
    "image": "images",
    "video": "broll",
}


def _write_via_contracts(**values: Any) -> Any | None:
    """Call the shared writer when its signature can accept this asset."""

    try:
        from vf_shared.contracts import assets as contract_assets
    except Exception:
        return None
    writer = getattr(contract_assets, "write_asset", None)
    if not callable(writer):
        return None

    try:
        parameters = set(_signature_parameters(writer))
    except (TypeError, ValueError):
        return None

    if {"project_id", "kind", "source_path_or_bytes"} <= parameters:
        content = values["data"] if values["data"] is not None else values["source_path"]
        if content is None:
            return None
        fields = _contract_fields(values)
        return writer(
            project_id=values["project_id"],
            kind=_contract_kind(str(values["kind"])),
            source_path_or_bytes=content,
            record_fields=fields,
        )

    if {"project_id", "relative_path"} <= parameters:
        kwargs = _keyword_fields(values, parameters)
        return writer(**kwargs)
    return None


@lru_cache(maxsize=16)
def _signature_parameters(writer: Any) -> tuple[str, ...]:
    import inspect

    return tuple(inspect.signature(writer).parameters)


def _keyword_fields(values: dict[str, Any], parameters: set[str]) -> dict[str, Any]:
    aliases = {
        "path": "relative_path",
        "name": "relative_path",
        "output": "relative_path",
        "asset": "relative_path",
        "asset_path": "relative_path",
        "extra": "metadata",
    }
    kwargs: dict[str, Any] = {}
    for parameter in parameters:
        source_name = parameter if parameter in values else aliases.get(parameter, "")
        if source_name:
            kwargs[parameter] = values[source_name]
    return kwargs


def _contract_fields(values: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "license": values["license"],
        "source": values["source"],
    }
    if values.get("cache_key"):
        fields["params_hash"] = values["cache_key"]
    suffix = Path(str(values.get("relative_path", ""))).suffix
    if suffix:
        fields["ext"] = suffix
    if values["source"].startswith("remote:"):
        fields["provider"] = "remote"
    else:
        fields["provider"] = "local"
    metadata = values.get("metadata") or {}
    for key in ("duration_sec", "width", "height", "sample_rate", "channels", "codec", "model"):
        if key in metadata and metadata[key] not in (None, ""):
            fields[key] = metadata[key]
    return fields


def _contract_kind(kind: str) -> str:
    return _KIND_ALIASES.get(kind, kind)


def _copy_if_needed(source: Path, target: Path) -> None:
    if source.resolve() == target.resolve():
        return
    if target.is_file() and _file_digest(target) == _file_digest(source):
        return
    shutil.copyfile(source, target)


def _write_sidecar(
    *,
    sidecar: Path,
    relative_path: str,
    project_id: str,
    kind: str,
    license: str,
    source: str,
    cache_key: str,
    digest: str,
    size: int,
    ai_generated: bool,
    metadata: dict[str, Any],
) -> None:
    payload = {
        "asset": relative_path,
        "project_id": project_id,
        "kind": kind,
        "license": license,
        "source": source,
        "cache_key": cache_key,
        "sha256": digest,
        "bytes": size,
        "ai_generated": ai_generated,
        "created_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "metadata": metadata,
    }
    sidecar.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
