"""Project workspace, asset sidecars, and idempotency keys for fetch tools."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import WorkspaceError
from .fetch_workspace_utils import (
    ContractAssetRecord,
    _contract_license,
    _default_workspace_root,
    _integer,
    _number,
    _read_json,
    _write_json,
    safe_filename,
    safe_project_id,
    sha256_file,
    stable_key,
    utc_now,
)

SCHEMA_VERSION = 1
ASSET_KINDS = ("broll", "images", "sfx")
ASSET_DIRECTORIES = {
    "broll": Path("assets") / "broll",
    "images": Path("assets") / "images",
    "sfx": Path("assets") / "sfx",
}


@dataclass(slots=True)
class Asset:
    """A materialized workspace asset plus its sidecars."""

    path: Path
    kind: str
    provider: str
    metadata: dict[str, Any] = field(default_factory=dict)
    license: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    cached: bool = False

    @property
    def sidecar_path(self) -> Path:
        return self.path.with_name(f"{self.path.name}.meta.json")

    @property
    def metadata_sidecar_path(self) -> Path:
        return self.path.with_name(f"{self.path.name}.metadata.json")

    @property
    def license_sidecar_path(self) -> Path:
        return self.path.with_name(f"{self.path.name}.license.json")

    @property
    def sha256(self) -> str:
        return str(self.metadata.get("sha256", ""))

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path.resolve()),
            "kind": self.kind,
            "provider": self.provider,
            "sidecar": str(self.sidecar_path.resolve()),
            "metadata_sidecar": str(self.metadata_sidecar_path.resolve()),
            "license_sidecar": str(self.license_sidecar_path.resolve()),
            "metadata": self.metadata,
            "license": self.license,
            "cached": self.cached,
        }


class Workspace:
    """Project-scoped asset store following the vf-contracts layout."""

    def __init__(self, project_id: str, root: str | Path | None = None) -> None:
        self.project_id = safe_project_id(project_id)
        base = Path(root).expanduser() if root is not None else _default_workspace_root()
        self.root = (base / "projects" / self.project_id).resolve()
        self.assets_root = self.root / "assets"
        self.cache_dir = self.root / ".cache"

    @staticmethod
    def key(payload: Mapping[str, Any]) -> str:
        return stable_key(payload)

    def directory(self, kind: str) -> Path:
        try:
            relative = ASSET_DIRECTORIES[kind]
        except KeyError as exc:
            raise WorkspaceError(f"Unknown asset kind {kind!r}") from exc
        path = self.root / relative
        path.mkdir(parents=True, exist_ok=True)
        return path

    def manifest_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def load_assets(self, key: str) -> list[Asset] | None:
        """Return cached assets for a key, or ``None`` on a miss."""

        payload = _read_json(self.manifest_path(key))
        if payload is not None:
            entries = payload.get("assets")
            if not isinstance(entries, list) or not entries:
                payload = None
            else:
                assets = self._load_manifest_assets(entries, key)
                if assets is not None:
                    return assets
        return self._scan_cached(key)

    def _load_manifest_assets(self, entries: list[Any], key: str) -> list[Asset] | None:
        assets: list[Asset] = []
        for entry in entries:
            if not isinstance(entry, dict):
                return None
            relative = entry.get("relative_path")
            if not isinstance(relative, str):
                return None
            path = (self.root / relative).resolve()
            if not path.is_relative_to(self.root) or not path.is_file():
                return None
            asset = self._read_asset(path, key)
            if asset is None:
                return None
            assets.append(asset)
        return assets

    def _scan_cached(self, key: str) -> list[Asset] | None:
        """Find contract sidecars by ``params_hash`` when no manifest exists."""

        matches: list[Asset] = []
        for kind in ASSET_KINDS:
            directory = self.root / "assets" / kind
            if not directory.is_dir():
                continue
            for meta in sorted(directory.glob("*.meta.json")):
                record = _read_json(meta)
                if record is None or record.get("params_hash") != key:
                    continue
                path = meta.with_name(meta.name.removesuffix(".meta.json"))
                if not path.is_file():
                    continue
                asset = self._read_asset(path, key)
                if asset is not None:
                    matches.append(asset)
        return matches or None

    def _read_asset(self, path: Path, key: str) -> Asset | None:
        record = _read_json(path.with_name(f"{path.name}.meta.json"))
        if record is None:
            return None
        rich = _read_json(path.with_name(f"{path.name}.metadata.json")) or {}
        license_doc = _read_json(path.with_name(f"{path.name}.license.json")) or {}
        license_payload = {
            name: value
            for name, value in license_doc.items()
            if name not in {"schema_version", "asset"}
        }
        metadata = {**record, **rich}
        return Asset(
            path=path,
            kind=str(record.get("kind", "")),
            provider=str(record.get("provider", "")),
            metadata=metadata,
            license=license_payload,
            idempotency_key=key,
            cached=True,
        )

    def save_manifest(self, key: str, assets: list[Asset], request: Mapping[str, Any]) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "idempotency_key": key,
            "created_at": utc_now(),
            "request": dict(request),
            "assets": [
                {
                    "relative_path": str(asset.path.relative_to(self.root)),
                    "kind": asset.kind,
                    "provider": asset.provider,
                    "sha256": asset.sha256,
                }
                for asset in assets
            ],
        }
        _write_json(self.manifest_path(key), payload)

    def import_file(
        self,
        source: str | Path,
        *,
        kind: str,
        name: str,
        provider: str,
        metadata: Mapping[str, Any],
        license: Mapping[str, Any],
        idempotency_key: str,
        move: bool = False,
    ) -> Asset:
        """Copy (or move) a file into the workspace and write its sidecars."""

        source_path = Path(source)
        if not source_path.is_file():
            raise WorkspaceError(f"Asset source is not a file: {source_path}")
        digest = sha256_file(source_path)
        suffix = Path(safe_filename(name, fallback=source_path.name)).suffix.lower()
        if not suffix or len(suffix) > 16:
            suffix = source_path.suffix.lower() or ".bin"
        target = self.directory(kind) / f"{digest}{suffix}"
        if not target.exists():
            if move:
                try:
                    shutil.move(str(source_path), target)
                except OSError as exc:
                    raise WorkspaceError(f"Cannot move asset into workspace: {exc}") from exc
            else:
                try:
                    shutil.copy2(source_path, target)
                except OSError as exc:
                    raise WorkspaceError(f"Cannot copy asset into workspace: {exc}") from exc

        metadata_doc = dict(metadata)
        metadata_doc.setdefault("provider", provider)
        metadata_doc.setdefault("name", safe_filename(name, fallback=target.name))
        metadata_doc["sha256"] = digest
        metadata_doc.setdefault("retrieved_at", utc_now())
        metadata_doc["size_bytes"] = target.stat().st_size
        metadata_doc["asset_id"] = f"{kind}-{digest[:16]}"
        metadata_doc["project_id"] = self.project_id
        metadata_doc["kind"] = kind
        metadata_doc["relative_path"] = str(target.relative_to(self.root))
        metadata_doc["params_hash"] = idempotency_key

        license_doc = dict(license)
        license_doc.setdefault("provider", provider)
        metadata_doc["license"] = dict(license_doc)
        record = self._record(
            target,
            kind=kind,
            provider=provider,
            digest=digest,
            metadata=metadata_doc,
            license=license_doc,
            idempotency_key=idempotency_key,
        )
        asset = Asset(
            path=target,
            kind=kind,
            provider=provider,
            metadata={**record, **metadata_doc},
            license=license_doc,
            idempotency_key=idempotency_key,
        )
        self._write_sidecars(asset, record)
        return asset

    def _record(
        self,
        target: Path,
        *,
        kind: str,
        provider: str,
        digest: str,
        metadata: Mapping[str, Any],
        license: Mapping[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        clip = metadata.get("clip")
        clip_duration = 0.0
        if isinstance(clip, Mapping):
            clip_duration = max(
                0.0,
                _number(clip.get("end")) - _number(clip.get("start")),
            )
        record: dict[str, Any] = {
            "asset_id": f"{kind}-{digest[:16]}",
            "project_id": self.project_id,
            "kind": kind,
            "path": f"assets/{kind}/{target.name}",
            "source": "mcp-fetch",
            "provider": provider,
            "model": "",
            "model_version": "",
            "url": str(metadata.get("page_url") or metadata.get("download_url") or ""),
            "license": _contract_license(provider, license),
            "attribution_required": bool(license.get("attribution_required")),
            "sha256": digest,
            "bytes": _integer(metadata.get("size_bytes")),
            "duration_sec": _number(metadata.get("duration")) or clip_duration,
            "sample_rate": _integer(metadata.get("sample_rate")),
            "channels": _integer(metadata.get("channels")),
            "codec": str(metadata.get("codec") or ""),
            "width": _integer(metadata.get("width")),
            "height": _integer(metadata.get("height")),
            "params_hash": idempotency_key,
            "created_at": str(metadata.get("retrieved_at") or utc_now()),
        }
        if ContractAssetRecord is not None:
            return ContractAssetRecord(**record).model_dump()
        return record

    def _write_sidecars(self, asset: Asset, record: Mapping[str, Any]) -> None:
        _write_json(asset.sidecar_path, record)
        _write_json(asset.metadata_sidecar_path, asset.metadata)
        _write_json(
            asset.license_sidecar_path,
            {
                "schema_version": SCHEMA_VERSION,
                "asset": {
                    "asset_id": record.get("asset_id"),
                    "path": record.get("path"),
                    "kind": record.get("kind"),
                    "provider": record.get("provider"),
                    "sha256": record.get("sha256"),
                },
                **asset.license,
            },
        )
