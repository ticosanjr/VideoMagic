"""Local image asset store for watermarks and overlays."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from videoflow.domain.errors import FilesystemError
from videoflow.runtime import portable_home

MAX_IMAGE_BYTES = 15 * 1024 * 1024
_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")


def images_dir() -> Path:
    directory = portable_home() / "assets" / "images"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def list_images() -> list[dict[str, object]]:
    return [
        {
            "file": str(path),
            "name": path.name,
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(images_dir().iterdir())
        if path.is_file() and path.suffix.casefold() in {".png", ".jpg", ".jpeg"}
    ]


def save_image(filename: str, data: bytes) -> dict[str, object]:
    if not data:
        raise FilesystemError("The image file is empty.")
    if len(data) > MAX_IMAGE_BYTES:
        raise FilesystemError("Images must be at most 15 MB.")
    if not data.startswith(_MAGIC):
        raise FilesystemError("Only PNG and JPEG images are supported.")
    suffix = Path(filename).suffix.casefold()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise FilesystemError("Use a .png, .jpg, or .jpeg filename.")
    digest = hashlib.sha256(data).hexdigest()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(filename).stem).strip("-") or "image"
    target = images_dir() / f"{stem}-{digest[:10]}{suffix}"
    target.write_bytes(data)
    return {
        "file": str(target),
        "name": target.name,
        "size_bytes": len(data),
        "sha256": digest,
    }
