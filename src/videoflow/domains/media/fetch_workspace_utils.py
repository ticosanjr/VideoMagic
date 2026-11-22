"""Workspace keys, safe names and atomic sidecar helpers for fetch tools."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:  # pragma: no cover - depends on the installed distribution
    from vf_shared.contracts.assets import AssetRecord as ContractAssetRecord
    from vf_shared.contracts.assets import asset_key as contract_asset_key
    from vf_shared.contracts.assets import sha256_file as contract_sha256_file
except ImportError:  # pragma: no cover - fallback for isolated source checkouts
    ContractAssetRecord = None  # type: ignore[assignment,misc]
    contract_asset_key = None  # type: ignore[assignment]
    contract_sha256_file = None  # type: ignore[assignment]

from .errors import InvalidRequestError

_SAFE_PROJECT = re.compile(r"[A-Za-z0-9_-]{1,128}")


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""

    return datetime.now(UTC).isoformat(timespec="seconds")


def _fallback_key(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def stable_key(payload: Mapping[str, Any]) -> str:
    """Hash a canonical request payload for cache/idempotency lookups."""

    if contract_asset_key is not None:
        values = dict(payload)
        tool = str(values.pop("tool", "asset"))
        return contract_asset_key(tool, values)
    return _fallback_key(payload)


def _fallback_sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: str | Path) -> str:
    """Hash a file without loading it into memory."""

    if contract_sha256_file is not None:
        return contract_sha256_file(path)
    return _fallback_sha256_file(Path(path))


def safe_project_id(project_id: str) -> str:
    """Reject project ids that could escape the workspace root."""

    value = str(project_id).strip()
    if not value or value in {".", ".."} or not _SAFE_PROJECT.fullmatch(value):
        raise InvalidRequestError(
            f"Invalid project_id {project_id!r}: use letters, digits, '_' or '-'."
        )
    return value


def safe_filename(name: str, *, fallback: str = "asset") -> str:
    """Return a single safe path component."""

    candidate = Path(str(name or "")).name
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "_", candidate).strip("._-")
    if not candidate:
        candidate = fallback
    if len(candidate) > 140:
        suffix = Path(candidate).suffix[:16]
        stem = Path(candidate).stem[: 140 - len(suffix)]
        candidate = f"{stem}{suffix}"
    return candidate


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _default_workspace_root() -> Path:
    override = os.environ.get("VF_WORKSPACE_ROOT")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".videoflow" / "workspace"


def _contract_license(provider: str, license_doc: Mapping[str, Any]) -> str:
    raw = " ".join(
        str(license_doc.get(key, "")) for key in ("license", "license_id", "license_url", "status")
    ).lower()
    if provider == "pexels" or "pexels" in raw:
        return "pexels"
    if provider == "pixabay" or "pixabay" in raw:
        return "pixabay"
    if "cc0" in raw or "publicdomain/zero" in raw:
        return "cc0"
    if provider == "yt-dlp" or "fair_use" in raw:
        return "youtube_fair_use"
    return "unknown"


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _integer(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
