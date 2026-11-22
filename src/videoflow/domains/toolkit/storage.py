"""Asset persistence with license/source sidecars and idempotent cache keys.

The preferred writer is ``vf_shared.contracts.assets.write_asset``. Each tool keeps a
stable project-relative working path (for example ``assets/broll/clip_zoom.mp4``)
while the shared contract stores the content-addressed copy and its own
``.meta.json`` sidecar. A local ``<file>.json`` sidecar holds the tool cache key
so repeated calls are idempotent even before the shared package is installed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import InvalidArgumentError, OutputNotProducedError
from .storage_contracts import (
    _copy_if_needed,
    _file_digest,
    _write_sidecar,
    _write_via_contracts,
)

_PROJECT_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_CONTRACT_LICENSES = {
    "cc0",
    "pexels",
    "pixabay",
    "ai_generated",
    "youtube_fair_use",
    "unknown",
}
_KIND_ALIASES = {
    "audio": "voice",
    "matte": "images",
    "upscaled": "images",
    "graphic": "graphics",
    "image": "images",
    "video": "broll",
}


@dataclass(frozen=True)
class AssetRecord:
    """One stored output asset and its sidecar metadata."""

    path: Path
    relative_path: str
    cache_key: str
    cached: bool
    sidecar: Path
    sha256: str = ""
    bytes_written: int = 0
    license: str = ""
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def cache_key(*parts: object) -> str:
    """Build a stable cache key from arbitrary JSON-serializable parts."""

    encoded = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def file_fingerprint(path: str | Path) -> str:
    """Cheap, stable identity for an input file used in cache keys."""

    resolved = Path(path).expanduser().resolve()
    stat = resolved.stat()
    return f"{resolved}:{stat.st_size}:{stat.st_mtime_ns}"


def project_dir(project_id: str) -> Path:
    """Resolve the output directory for a project."""

    if not project_id or not _PROJECT_ID.fullmatch(project_id):
        raise InvalidArgumentError(
            f"invalid project_id: {project_id!r}",
            details={"project_id": project_id},
        )
    override = os.environ.get("VF_PROJECT_OUTPUT")
    if override:
        return Path(override).expanduser().resolve()
    shared = _shared_project_dir(project_id)
    if shared is not None:
        return shared
    root = os.environ.get("VF_PROJECTS_ROOT")
    if root:
        base = Path(root).expanduser()
        if base.name != "projects":
            base = base / "projects"
        return (base / project_id).resolve()
    return (Path.home() / ".videoflow" / "projects" / project_id).resolve()


def safe_relative_path(relative_path: str) -> str:
    """Reject absolute paths and traversal before writing inside a project."""

    cleaned = str(relative_path).replace("\\", "/").strip()
    parts = [part for part in cleaned.split("/") if part not in ("", ".")]
    if not cleaned or Path(cleaned).is_absolute() or any(part == ".." for part in parts):
        raise InvalidArgumentError(
            f"unsafe asset path: {relative_path!r}",
            details={"relative_path": relative_path},
        )
    return "/".join(parts)


def asset_path(project_id: str, relative_path: str) -> Path:
    return project_dir(project_id) / safe_relative_path(relative_path)


def sidecar_path(path: Path) -> Path:
    return path.with_name(path.name + ".json")


def cached_asset(project_id: str, relative_path: str, key: str) -> AssetRecord | None:
    """Return an existing asset when its sidecar carries the same cache key."""

    path = asset_path(project_id, relative_path)
    sidecar = sidecar_path(path)
    if not path.is_file() or not sidecar.is_file():
        return None
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("cache_key") != key:
        return None
    return AssetRecord(
        path=path,
        relative_path=safe_relative_path(relative_path),
        cache_key=key,
        cached=True,
        sidecar=sidecar,
        sha256=str(payload.get("sha256", "")),
        bytes_written=int(payload.get("bytes", 0) or 0),
        license=str(payload.get("license", "")),
        source=str(payload.get("source", "")),
        metadata=dict(payload.get("metadata") or {}),
    )


def write_output(
    project_id: str,
    relative_path: str,
    *,
    data: bytes | None = None,
    source_path: str | Path | None = None,
    kind: str = "asset",
    license: str = "generated",
    source: str = "generated",
    cache_key: str = "",
    metadata: dict[str, Any] | None = None,
    ai_generated: bool = False,
) -> AssetRecord:
    """Store one output through `vf_shared.contracts.assets.write_asset`."""

    if data is not None and source_path is not None:
        raise InvalidArgumentError("write_output accepts data or source_path, not both")
    relative = safe_relative_path(relative_path)
    target = project_dir(project_id) / relative

    existing = cached_asset(project_id, relative, cache_key) if cache_key else None
    if existing is not None:
        return existing

    target.parent.mkdir(parents=True, exist_ok=True)
    shared_license = contract_license(license, ai_generated=ai_generated)
    external = _write_via_contracts(
        project_id=project_id,
        relative_path=relative,
        data=data,
        source_path=source_path,
        kind=kind,
        license=shared_license,
        source=source,
        cache_key=cache_key,
        metadata=dict(metadata or {}),
        ai_generated=ai_generated,
    )

    if external is not None:
        stored = _absolute_result_path(external, project_id, target)
        if not stored.is_file():
            raise OutputNotProducedError(
                "vf_shared.contracts.assets.write_asset did not store the asset",
                details={"path": str(stored)},
            )
        _copy_if_needed(stored, target)
        digest = _file_digest(stored)
        size = stored.stat().st_size
        sidecar = sidecar_path(target)
        _write_sidecar(
            sidecar=sidecar,
            relative_path=relative,
            project_id=project_id,
            kind=kind,
            license=shared_license,
            source=source,
            cache_key=cache_key,
            digest=digest,
            size=size,
            ai_generated=ai_generated,
            metadata=dict(metadata or {}),
        )
        return AssetRecord(
            path=target,
            relative_path=relative,
            cache_key=cache_key,
            cached=False,
            sidecar=sidecar,
            sha256=digest,
            bytes_written=size,
            license=shared_license,
            source=source,
            metadata=dict(metadata or {}),
        )

    if source_path is not None:
        origin = Path(source_path).expanduser()
        if not origin.is_file():
            raise OutputNotProducedError(
                f"expected output was not produced: {origin}",
                details={"path": str(origin)},
            )
        if origin.resolve() != target.resolve():
            shutil.copyfile(origin, target)
    elif data is not None:
        target.write_bytes(data)
    else:
        raise InvalidArgumentError("write_output needs data or source_path")

    size = target.stat().st_size
    digest = _file_digest(target)
    sidecar = sidecar_path(target)
    _write_sidecar(
        sidecar=sidecar,
        relative_path=relative,
        project_id=project_id,
        kind=kind,
        license=shared_license,
        source=source,
        cache_key=cache_key,
        digest=digest,
        size=size,
        ai_generated=ai_generated,
        metadata=dict(metadata or {}),
    )
    return AssetRecord(
        path=target,
        relative_path=relative,
        cache_key=cache_key,
        cached=False,
        sidecar=sidecar,
        sha256=digest,
        bytes_written=size,
        license=shared_license,
        source=source,
        metadata=dict(metadata or {}),
    )


def contract_license(license: str, *, ai_generated: bool = False) -> str:
    """Map tool license labels onto the shared contract's license enum."""

    if ai_generated or license in {"generated", "ai_generated"}:
        return "ai_generated"
    if license in _CONTRACT_LICENSES:
        return license
    return "unknown"


def _shared_project_dir(project_id: str) -> Path | None:
    try:
        from vf_shared.contracts.workspace import project_dir as shared_project_dir
    except Exception:
        return None
    try:
        return Path(shared_project_dir(project_id)).expanduser().resolve()
    except Exception:
        return None


def _absolute_result_path(result: Any, project_id: str, default: Path) -> Path:
    path = _result_path(result, default)
    if not path.is_absolute():
        # ``vf_shared.contracts`` always stores under its own workspace project dir,
        # which may differ from VF_PROJECT_OUTPUT. Resolve relative results
        # against the writer's root, not the tool's preferred output root.
        path = (_shared_project_dir(project_id) or project_dir(project_id)) / path
    return path


def _result_path(result: Any, default: Path) -> Path:
    if isinstance(result, (str, Path)):
        return Path(str(result))
    if isinstance(result, dict):
        for key in ("path", "output", "asset_path", "file"):
            value = result.get(key)
            if value:
                return Path(str(value))
    for attribute in ("path", "output", "file"):
        value = getattr(result, attribute, None)
        if value:
            return Path(str(value))
    return default


