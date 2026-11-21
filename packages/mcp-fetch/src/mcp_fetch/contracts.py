"""Workspace/assets contract surface.

``vf-contracts`` owns the shared workspace layout, ``AssetRecord`` sidecars, and
idempotency keys for VideoFlow 2.90. This module re-exports the contract
functions when the sibling package is importable and always re-exports this
package's ``Workspace``/``Asset`` implementation, which writes the same layout
and sidecar schema.
"""

from __future__ import annotations

from .workspace import Asset, Workspace, sha256_file, stable_key

try:  # pragma: no cover - depends on the installed distribution
    from vf_shared.contracts.assets import (
        AssetRecord,
        asset_key,
        find_cached,
        read_sidecar,
        sidecar_path,
        write_asset,
    )
    from vf_shared.contracts.workspace import ASSET_KINDS, project_dir, resolve_within

    CONTRACTS_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback for isolated source checkouts
    AssetRecord = None  # type: ignore[assignment,misc]
    asset_key = None  # type: ignore[assignment]
    find_cached = None  # type: ignore[assignment]
    read_sidecar = None  # type: ignore[assignment]
    sidecar_path = None  # type: ignore[assignment]
    write_asset = None  # type: ignore[assignment]
    ASSET_KINDS = ("broll", "images", "sfx")
    project_dir = None  # type: ignore[assignment]
    resolve_within = None  # type: ignore[assignment]
    CONTRACTS_AVAILABLE = False

__all__ = [
    "ASSET_KINDS",
    "CONTRACTS_AVAILABLE",
    "Asset",
    "AssetRecord",
    "Workspace",
    "asset_key",
    "find_cached",
    "project_dir",
    "read_sidecar",
    "resolve_within",
    "sha256_file",
    "sidecar_path",
    "stable_key",
    "write_asset",
]
