"""Small shared store for music and SFX files."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path

from videoflow.domain.errors import FilesystemError


def list_files(directory: Path, suffixes: Iterable[str]) -> list[dict[str, object]]:
    allowed = set(suffixes)
    return [
        {"file": str(path), "name": path.name, "size_bytes": path.stat().st_size}
        for path in sorted(directory.iterdir())
        if path.is_file() and path.suffix.casefold() in allowed
    ]


def save_file(
    filename: str,
    data: bytes,
    *,
    directory: Path,
    suffixes: Iterable[str],
    max_bytes: int,
    label: str,
    default_stem: str,
) -> dict[str, object]:
    allowed = set(suffixes)
    if not data:
        raise FilesystemError(f"The {label} file is empty.")
    if len(data) > max_bytes:
        raise FilesystemError(
            f"{label.capitalize()} files must be at most {max_bytes // (1024 * 1024)} MB."
        )
    suffix = Path(filename).suffix.casefold()
    if suffix not in allowed:
        raise FilesystemError(
            "Use " + ", ".join(sorted(allowed)) + "."
        )
    digest = hashlib.sha256(data).hexdigest()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(filename).stem).strip("-") or default_stem
    target = directory / f"{stem}-{digest[:10]}{suffix}"
    target.write_bytes(data)
    return {
        "file": str(target),
        "name": target.name,
        "size_bytes": len(data),
        "sha256": digest,
    }
