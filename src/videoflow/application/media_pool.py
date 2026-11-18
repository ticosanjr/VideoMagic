"""Content-addressed media pool using hardlinks with safe fallbacks."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from vf_contracts.workspace import workspace_root


def pool_root() -> Path:
    directory = Path(workspace_root()).expanduser() / "_pool"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def link_or_copy(source: Path, target: Path) -> Path:
    """Prefer a hardlink, then a symlink, then a regular copy."""

    source = Path(source).expanduser()
    target = Path(target).expanduser()
    if source.resolve() == target.resolve():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return target
    try:
        os.link(source, target)
        return target
    except OSError:
        pass
    try:
        target.symlink_to(source)
        return target
    except OSError:
        shutil.copy2(source, target)
        return target


def pool_file(source: Path, *, kind: str = "media", digest: str = "") -> Path:
    """Link one file into ``{workspace}/_pool/{sha256}/`` and return the pool path."""

    source = Path(source).expanduser()
    if not source.is_file():
        return source
    content_digest = digest or file_sha256(source)
    filename = source.name if source.name.startswith(f"{kind}-") else f"{kind}-{source.name}"
    target = pool_root() / content_digest / filename
    return link_or_copy(source, target)


__all__ = ["file_sha256", "link_or_copy", "pool_file", "pool_root"]
