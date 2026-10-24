"""Sound-effect asset store."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from videoflow.domain.errors import AssetNotFoundError, FilesystemError
from videoflow.runtime import portable_home

MAX_SFX_BYTES = 50 * 1024 * 1024
_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


def sfx_dir() -> Path:
    directory = portable_home() / "assets" / "sfx"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def list_sfx() -> list[dict[str, object]]:
    return [
        {"file": str(path), "name": path.name, "size_bytes": path.stat().st_size}
        for path in sorted(sfx_dir().iterdir())
        if path.is_file() and path.suffix.casefold() in _SUFFIXES
    ]


def save_sfx(filename: str, data: bytes) -> dict[str, object]:
    if not data:
        raise FilesystemError("The SFX file is empty.")
    if len(data) > MAX_SFX_BYTES:
        raise FilesystemError("SFX files must be at most 50 MB.")
    suffix = Path(filename).suffix.casefold()
    if suffix not in _SUFFIXES:
        raise FilesystemError("Use .mp3, .wav, .m4a, .aac, .ogg, or .flac.")
    digest = hashlib.sha256(data).hexdigest()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(filename).stem).strip("-") or "sfx"
    target = sfx_dir() / f"{stem}-{digest[:10]}{suffix}"
    target.write_bytes(data)
    return {
        "file": str(target),
        "name": target.name,
        "size_bytes": len(data),
        "sha256": digest,
    }


def delete_sfx(name: str) -> None:
    target = sfx_dir() / Path(name).name
    if target.parent != sfx_dir() or not target.is_file():
        raise AssetNotFoundError(f"Unknown SFX asset: {name}")
    target.unlink()
