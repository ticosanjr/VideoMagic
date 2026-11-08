"""Sound-effect asset store."""

from __future__ import annotations

from pathlib import Path

from videoflow.application.asset_store import list_files, save_file
from videoflow.domain.errors import AssetNotFoundError
from videoflow.runtime import portable_home

MAX_SFX_BYTES = 50 * 1024 * 1024
_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


def sfx_dir() -> Path:
    directory = portable_home() / "assets" / "sfx"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def list_sfx() -> list[dict[str, object]]:
    return list_files(sfx_dir(), _SUFFIXES)


def save_sfx(filename: str, data: bytes) -> dict[str, object]:
    return save_file(
        filename,
        data,
        directory=sfx_dir(),
        suffixes=_SUFFIXES,
        max_bytes=MAX_SFX_BYTES,
        label="SFX",
        default_stem="sfx",
    )


def delete_sfx(name: str) -> None:
    target = sfx_dir() / Path(name).name
    if target.parent != sfx_dir() or not target.is_file():
        raise AssetNotFoundError(f"Unknown SFX asset: {name}")
    target.unlink()
