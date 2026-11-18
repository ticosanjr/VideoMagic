"""Channel brand-kit discovery for logos, lower thirds, CTAs, LUTs, and stings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.runtime import portable_home

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".m4v"}
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".ogg"}


def brand_kit_root(channel_id: str) -> Path:
    return portable_home() / "brands" / str(channel_id).strip()


def load_brand_kit(channel_id: str) -> dict[str, Any]:
    root = brand_kit_root(channel_id)
    if not root.is_dir():
        return {"channel_id": channel_id, "path": str(root), "exists": False, "assets": {}}
    assets: dict[str, list[str]] = {
        "logo": [],
        "lower_third": [],
        "cta": [],
        "lut": [],
        "music": [],
        "sting": [],
    }
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.casefold()
        name = path.name.casefold()
        if suffix == ".cube":
            assets["lut"].append(str(path))
        elif "logo" in name and suffix in IMAGE_SUFFIXES:
            assets["logo"].append(str(path))
        elif ("lower" in name or "third" in name) and suffix in IMAGE_SUFFIXES:
            assets["lower_third"].append(str(path))
        elif ("cta" in name or "card" in name) and suffix in IMAGE_SUFFIXES | VIDEO_SUFFIXES:
            assets["cta"].append(str(path))
        elif suffix in AUDIO_SUFFIXES and ("sting" in name or "vignette" in name):
            assets["sting"].append(str(path))
        elif suffix in AUDIO_SUFFIXES:
            assets["music"].append(str(path))
    return {
        "channel_id": channel_id,
        "path": str(root),
        "exists": True,
        "assets": assets,
        "logo": assets["logo"][0] if assets["logo"] else "",
        "lower_third": assets["lower_third"][0] if assets["lower_third"] else "",
        "cta": assets["cta"][0] if assets["cta"] else "",
        "lut": assets["lut"][0] if assets["lut"] else "",
        "music": assets["music"][0] if assets["music"] else "",
        "sting": assets["sting"][0] if assets["sting"] else "",
    }


__all__ = ["brand_kit_root", "load_brand_kit"]
