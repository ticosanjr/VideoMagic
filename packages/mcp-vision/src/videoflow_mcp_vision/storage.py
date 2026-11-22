"""Compatibility shim for the vision asset store."""

from __future__ import annotations

from videoflow.domains.vision.storage import (
    AssetRecord,
    asset_path,
    cache_key,
    cached_asset,
    contract_license,
    file_fingerprint,
    project_dir,
    safe_relative_path,
    sidecar_path,
    write_output,
)

__all__ = [
    "AssetRecord",
    "asset_path",
    "cache_key",
    "cached_asset",
    "contract_license",
    "file_fingerprint",
    "project_dir",
    "safe_relative_path",
    "sidecar_path",
    "write_output",
]
