"""Local asset library: index, scan, search, and removal."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from videoflow.runtime import portable_home

VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
FONT = {".ttf", ".otf", ".woff", ".woff2"}
ALL = VIDEO | AUDIO | IMAGE | FONT


def library_dir() -> Path:
    directory = portable_home() / "assets"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def index_path() -> Path:
    return library_dir() / "index.json"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _kind(suffix: str) -> str:
    value = suffix.casefold()
    if value in VIDEO:
        return "video"
    if value in AUDIO:
        return "audio"
    if value in IMAGE:
        return "image"
    if value in FONT:
        return "font"
    return "other"


def _read() -> list[dict[str, Any]]:
    try:
        payload = json.loads(index_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    assets = payload.get("assets") if isinstance(payload, dict) else None
    return [item for item in assets if isinstance(item, dict)] if isinstance(assets, list) else []


def _write(assets: list[dict[str, Any]]) -> None:
    path = index_path()
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps({"ok": True, "assets": assets}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _record(path: Path, tags: list[str] | None = None) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    stat = resolved.stat()
    asset_id = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:16]
    return {
        "id": asset_id,
        "path": str(resolved),
        "name": resolved.name,
        "kind": _kind(resolved.suffix),
        "suffix": resolved.suffix.casefold(),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(timespec="seconds"),
        "added_at": _now(),
        "tags": sorted({str(tag).strip() for tag in (tags or []) if str(tag).strip()}),
        "license": "operator",
        "source": "local",
    }


def scan_directory(
    directory: Path,
    *,
    tags: list[str] | None = None,
    recursive: bool = True,
) -> list[dict[str, Any]]:
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        return []
    pattern = "**/*" if recursive else "*"
    records: list[dict[str, Any]] = []
    for path in sorted(root.glob(pattern)):
        if not path.is_file() or path.suffix.casefold() not in ALL:
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        try:
            records.append(_record(path, tags))
        except OSError:
            continue
    existing = {item["id"]: item for item in _read()}
    for item in records:
        existing[item["id"]] = item
    _write(list(existing.values()))
    return records


def list_assets(query: str = "", kind: str = "", limit: int = 500) -> list[dict[str, Any]]:
    needle = query.strip().casefold()
    assets = _read()
    if kind:
        assets = [item for item in assets if item.get("kind") == kind]
    if needle:
        assets = [
            item
            for item in assets
            if needle in str(item.get("name", "")).casefold()
            or needle in str(item.get("path", "")).casefold()
            or any(needle in str(tag).casefold() for tag in item.get("tags", []))
        ]
    assets.sort(key=lambda item: str(item.get("added_at", "")), reverse=True)
    return assets[: max(1, min(int(limit), 2000))]


def get_asset(asset_id: str) -> dict[str, Any] | None:
    return next((item for item in _read() if item.get("id") == asset_id), None)


def remove_asset(asset_id: str) -> bool:
    assets = _read()
    kept = [item for item in assets if item.get("id") != asset_id]
    if len(kept) == len(assets):
        return False
    _write(kept)
    return True


def update_tags(asset_id: str, tags: list[str]) -> dict[str, Any] | None:
    assets = _read()
    for item in assets:
        if item.get("id") == asset_id:
            item["tags"] = sorted({str(tag).strip() for tag in tags if str(tag).strip()})
            _write(assets)
            return item
    return None
