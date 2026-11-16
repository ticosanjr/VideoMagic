"""Asset records and content-addressed storage for a VideoFlow workspace."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from vf_contracts.workspace import (
    _validate_name,
    project_dir,
    resolve_within,
    validate_project_id,
)

License = Literal[
    "cc0",
    "pexels",
    "pixabay",
    "ai_generated",
    "youtube_fair_use",
    "unknown",
]

_SIDECAR_SUFFIX = ".meta.json"
_EXT_RE = re.compile(r"^\.[A-Za-z0-9]{1,16}$")
_CHUNK_SIZE = 1024 * 1024


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class AssetRecord(BaseModel):
    """Durable description of one asset stored in a project."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str
    project_id: str
    kind: str
    path: str
    source: str = "unknown"
    provider: str = ""
    model: str = ""
    model_version: str = ""
    url: str = ""
    license: License = "unknown"
    attribution_required: bool = False
    sha256: str = ""
    bytes: int = 0
    duration_sec: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    codec: str = ""
    width: int = 0
    height: int = 0
    params_hash: str = ""
    created_at: str = ""


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        items = sorted(value.items(), key=lambda kv: str(kv[0]))
        return {str(key): _normalize(item) for key, item in items}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def asset_key(
    tool: str,
    params: Mapping[str, Any] | None,
    model: str = "",
    version: str = "",
) -> str:
    """Return a deterministic sha256 key for a tool invocation.

    Dictionary order, nesting and tuples are normalized before hashing, so
    equivalent parameter sets always produce the same key.
    """

    canonical = {
        "tool": str(tool),
        "params": _normalize(dict(params or {})),
        "model": str(model),
        "version": str(version),
    }
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path, chunk_size: int = _CHUNK_SIZE) -> str:
    """Stream a file through sha256 without loading it into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def sidecar_path(path: str | Path) -> Path:
    """Return the sidecar path for a stored asset file."""

    source = Path(path)
    if source.name.endswith(_SIDECAR_SUFFIX):
        return source
    return Path(f"{source}{_SIDECAR_SUFFIX}")


def read_sidecar(path: str | Path) -> AssetRecord:
    """Read an asset record from either the stored file or its sidecar."""

    meta = sidecar_path(path)
    return AssetRecord.model_validate_json(meta.read_text(encoding="utf-8"))


def iter_assets(project_id: str, kind: str | None = None) -> Iterator[AssetRecord]:
    """Yield asset records for a project, optionally restricted to one kind."""

    assets_root = project_dir(project_id) / "assets"
    if kind is not None:
        directories = [assets_root / _validate_name(kind, "asset kind")]
    elif assets_root.is_dir():
        directories = sorted(item for item in assets_root.iterdir() if item.is_dir())
    else:
        directories = []

    for directory in directories:
        if not directory.is_dir():
            continue
        for meta in sorted(directory.glob(f"*{_SIDECAR_SUFFIX}")):
            try:
                yield read_sidecar(meta)
            except (OSError, ValueError, ValidationError):
                continue


def find_cached(project_id: str, kind: str, key: str) -> AssetRecord | None:
    """Return the stored asset matching an asset key or asset id."""

    for record in iter_assets(project_id, kind):
        if record.params_hash == key or record.asset_id == key:
            return record
    return None


def _normalize_ext(value: str | None) -> str:
    if not value:
        return ""
    ext = value if value.startswith(".") else f".{value}"
    if not _EXT_RE.fullmatch(ext):
        raise ValueError(f"invalid asset extension: {value!r}")
    return ext.lower()


def _atomic_write_bytes(destination: Path, data: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(destination.parent),
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, destination)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _atomic_copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(destination.parent),
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out_handle, source.open("rb") as in_handle:
            shutil.copyfileobj(in_handle, out_handle, length=_CHUNK_SIZE)
            out_handle.flush()
            os.fsync(out_handle.fileno())
        os.replace(tmp_path, destination)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


@contextlib.contextmanager
def _index_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl
    except ImportError:  # pragma: no cover - non-POSIX fallback
        yield
        return

    with lock_path.open("a+", encoding="utf-8") as handle:
        with contextlib.suppress(OSError):
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            with contextlib.suppress(OSError):
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_index(index_path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, Mapping):
        raw = payload.get("assets", [])
    else:
        return []
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _update_index(project_id: str, record: AssetRecord) -> None:
    assets_root = project_dir(project_id) / "assets"
    index_path = assets_root / "index.json"
    lock_path = assets_root / ".index.lock"

    with _index_lock(lock_path):
        entries = _read_index(index_path)
        entries = [
            entry
            for entry in entries
            if entry.get("asset_id") != record.asset_id and entry.get("path") != record.path
        ]
        entries.append(record.model_dump())
        entries.sort(key=lambda entry: str(entry.get("asset_id", "")))
        payload = {"version": 1, "assets": entries}
        _atomic_write_bytes(
            index_path,
            (json.dumps(payload, indent=2, sort_keys=False) + "\n").encode("utf-8"),
        )


def write_asset(
    project_id: str,
    kind: str,
    source_path_or_bytes: str | Path | bytes | bytearray | memoryview,
    record_fields: Mapping[str, Any] | None = None,
) -> AssetRecord:
    """Copy content into ``assets/<kind>/<sha256><ext>`` and record metadata.

    ``record_fields`` accepts :class:`AssetRecord` fields plus optional
    ``tool``/``params``/``ext`` helpers. The operation is idempotent: writing
    identical content again reuses the file, asset id, sidecar and created_at.
    """

    project_id = validate_project_id(project_id)
    kind = _validate_name(kind, "asset kind")
    root = project_dir(project_id)
    fields = dict(record_fields or {})

    tool = str(fields.pop("tool", kind))
    params = fields.pop("params", None)
    key_alias = fields.pop("key", None)
    ext_hint = _normalize_ext(fields.pop("ext", None))

    source_path: Path | None = None
    if isinstance(source_path_or_bytes, (bytes, bytearray, memoryview)):
        data = bytes(source_path_or_bytes)
        digest = hashlib.sha256(data).hexdigest()
        size = len(data)
        ext = ext_hint or _normalize_ext(Path(str(fields.get("path", ""))).suffix) or ".bin"
    else:
        source_path = Path(source_path_or_bytes)
        if not source_path.is_file():
            raise FileNotFoundError(f"asset source not found: {source_path}")
        digest = sha256_file(source_path)
        size = source_path.stat().st_size
        ext = _normalize_ext(source_path.suffix) or ext_hint or ".bin"

    file_name = f"{digest}{ext}"
    destination = root / "assets" / kind / file_name
    if not destination.is_file():
        if source_path is None:
            _atomic_write_bytes(destination, bytes(source_path_or_bytes))
        else:
            _atomic_copy_file(source_path, destination)

    meta = sidecar_path(destination)
    created_at = str(fields.get("created_at") or "")
    if not created_at and meta.is_file():
        with contextlib.suppress(OSError, ValueError, ValidationError):
            created_at = read_sidecar(meta).created_at
    if not created_at:
        created_at = _utc_now()

    params_hash = str(fields.get("params_hash") or key_alias or "") or asset_key(
        tool,
        params if isinstance(params, Mapping) else None,
        str(fields.get("model", "")),
        str(fields.get("model_version", "")),
    )

    values: dict[str, Any] = dict(fields)
    values.update(
        {
            "asset_id": str(fields.get("asset_id") or f"{kind}-{digest[:16]}"),
            "project_id": project_id,
            "kind": kind,
            "path": f"assets/{kind}/{file_name}",
            "sha256": digest,
            "bytes": size,
            "params_hash": params_hash,
            "created_at": created_at,
        }
    )
    record = AssetRecord(**values)

    _atomic_write_bytes(
        meta,
        (record.model_dump_json(indent=2) + "\n").encode("utf-8"),
    )
    with contextlib.suppress(OSError, ValueError, TypeError):
        _update_index(project_id, record)
    return record


__all__ = [
    "AssetRecord",
    "License",
    "asset_key",
    "find_cached",
    "iter_assets",
    "read_sidecar",
    "resolve_within",
    "sha256_file",
    "sidecar_path",
    "write_asset",
]
