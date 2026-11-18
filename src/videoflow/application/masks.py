"""Cached alpha masks for rounded-window rendering."""

from __future__ import annotations

from pathlib import Path

from videoflow.runtime import cache_root


def mask_root() -> Path:
    directory = cache_root() / "masks"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def rounded_mask_path(width: int, height: int, radius: int) -> Path:
    return mask_root() / f"rounded_{width}x{height}_r{max(0, radius)}.png"


def ensure_rounded_mask(width: int, height: int, radius: int) -> Path | None:
    """Create a white rounded rectangle on black, cached by dimensions/radius.

    Returns ``None`` when Pillow is unavailable so the renderer can fall back to
    the legacy per-pixel ``geq`` graph.
    """

    width = max(2, int(width))
    height = max(2, int(height))
    radius = max(0, min(width, height, int(radius)))
    target = rounded_mask_path(width, height, radius)
    if target.is_file():
        return target
    try:
        from PIL import Image, ImageDraw
    except Exception:  # noqa: BLE001 - optional dependency
        return None
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    if radius > 0:
        draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
    else:
        draw.rectangle((0, 0, width - 1, height - 1), fill=255)
    temporary = target.with_name(f".{target.name}.tmp")
    image.save(temporary, format="PNG")
    temporary.replace(target)
    return target


__all__ = ["ensure_rounded_mask", "mask_root", "rounded_mask_path"]
