"""One predictable root folder for final videos, exports, and scene assets."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Literal

DELIVERY_ROOT_NAME = "VideoFlow_Output"
CATEGORIES = ("videos", "exports", "shorts", "scenes")
_MEDIA_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
_SIDECAR_SUFFIXES = {
    ".fcpxml",
    ".xml",
    ".kdenlive",
    ".mlt",
    ".edl",
    ".ass",
    ".srt",
    ".vtt",
    ".json",
    ".zip",
    ".png",
    ".jpg",
    ".jpeg",
}


def delivery_root() -> Path:
    override = os.environ.get("VF_OUTPUT_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    try:
        from videoflow.application.settings import load_settings
        from videoflow.runtime import portable_home

        configured = load_settings().paths.output_root.strip()
        if configured:
            return Path(configured).expanduser() / DELIVERY_ROOT_NAME
        if (Path.cwd() / ".videoflow").is_dir() or (Path.cwd() / "opencode.json").is_file():
            return Path.cwd() / DELIVERY_ROOT_NAME
        return portable_home() / DELIVERY_ROOT_NAME
    except Exception:  # noqa: BLE001 - path discovery must not block a job
        return Path.cwd() / DELIVERY_ROOT_NAME


def _add_candidate(
    source: Path,
    items: list[tuple[str, Path]],
    category: str,
    path: Path,
) -> None:
    if not path.is_file():
        return
    try:
        relative = path.relative_to(source)
    except ValueError:
        return
    item = (category, relative)
    if item not in items:
        items.append(item)


def _required_candidates(source: Path) -> list[tuple[str, Path]]:
    """Explicit delivery contract, independent of the generic suffix scan."""

    items: list[tuple[str, Path]] = []
    for name in ("youtube_master.mp4", "preview_fast.mp4"):
        _add_candidate(source, items, "exports", source / "exports" / name)
    exports = source / "exports"
    if exports.is_dir():
        for suffix in (".fcpxml", ".xml", ".kdenlive", ".mlt"):
            for path in sorted(exports.glob(f"*{suffix}")):
                _add_candidate(source, items, "exports", path)
        qa = exports / "qa"
        if qa.is_dir():
            for path in sorted(qa.rglob("*")):
                _add_candidate(source, items, "exports", path)
    batch = source / "shorts" / "batch"
    if batch.is_dir():
        for suffix in (".mp4", ".ass"):
            for path in sorted(batch.glob(f"*{suffix}")):
                _add_candidate(source, items, "shorts", path)
    return items


def _candidates(source: Path) -> list[tuple[str, Path]]:
    items: list[tuple[str, Path]] = []
    for category in CATEGORIES:
        root = source / category
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.casefold() not in (
                _MEDIA_SUFFIXES | _SIDECAR_SUFFIXES
            ):
                continue
            _add_candidate(source, items, category, path)
    # A finalized video may be written directly at the project root.
    for path in source.glob("*.mp4"):
        _add_candidate(source, items, "videos", path)
    for item in _required_candidates(source):
        if item not in items:
            items.append(item)
    return items


def collect_outputs(
    source: Path,
    *,
    project_id: str = "",
    mode: Literal["copy", "move"] = "copy",
) -> dict[str, Any]:
    """Copy or move final project artifacts under the delivery root."""

    source = Path(source).expanduser().resolve()
    root = delivery_root().expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    moved: list[str] = []
    skipped: list[str] = []
    warnings: list[str] = []
    for category, relative in _candidates(source):
        source_path = source / relative
        try:
            inner = relative.relative_to(category)
        except ValueError:
            inner = Path(relative.name)
        destination = root / (project_id or "shared") / category / inner
        if destination.exists() and destination.stat().st_size == source_path.stat().st_size:
            skipped.append(str(destination))
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        effective_mode = mode
        if category == "scenes" and mode == "move":
            # Scene manifests store absolute keyframe paths; moving them would
            # invalidate the cache. Copy the scene cache instead.
            effective_mode = "copy"
            warnings.append(
                f"scene cache copied instead of moved: {source_path}"
            )
        if effective_mode == "move":
            shutil.move(str(source_path), str(destination))
            moved.append(str(destination))
        else:
            shutil.copy2(source_path, destination)
            copied.append(str(destination))
    manifest = {
        "schema_version": 1,
        "source": str(source),
        "root": str(root),
        "project_id": project_id,
        "mode": mode,
        "copied": copied,
        "moved": moved,
        "skipped": skipped,
        "warnings": warnings,
        "count": len(copied) + len(moved),
    }
    target = root / "manifests" / f"{project_id or 'shared'}-collect.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    manifest["manifest_path"] = str(target)
    return manifest
