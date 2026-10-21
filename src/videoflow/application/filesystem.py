"""Local filesystem browsing for the rack UI.

The browser never uploads media. It lists paths that pass the same allowlist as
the job API, which keeps the local server from becoming a general file reader.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from videoflow.domain.errors import (
    DirectoryExistsError,
    FilesystemError,
    InvalidDirectoryNameError,
    PathJailError,
    PathNotDirectoryError,
    PathNotFoundError,
    PermissionDeniedError,
)
from videoflow.domain.paths import resolve_allowed
from videoflow.runtime import allowed_roots, portable_home

FileMode = Literal["file", "directory"]
DEFAULT_LIMIT = 500
MAX_LIMIT = 2000
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def roots_payload(roots: Sequence[Path] | None = None) -> list[dict[str, object]]:
    """Return unique allowed roots with friendly labels for quick navigation."""

    items: list[dict[str, object]] = []
    seen: set[Path] = set()
    for root in _normalise_roots(roots):
        if root in seen:
            continue
        seen.add(root)
        items.append(
            {
                "name": _root_label(root),
                "path": str(root),
                "exists": root.is_dir(),
                "writable": _writable(root),
            }
        )
    return items


def list_directory(
    path: str | Path | None = None,
    *,
    mode: FileMode = "file",
    extensions: Sequence[str] = (),
    query: str = "",
    show_hidden: bool = False,
    limit: int = DEFAULT_LIMIT,
    roots: Sequence[Path] | None = None,
) -> dict[str, object]:
    """List one directory, returning only entries that stay inside the allowlist."""

    if mode not in {"file", "directory"}:
        raise ValueError(f"Unsupported filesystem mode: {mode}")
    normalised_roots = _normalise_roots(roots)
    current = _resolve_directory(path, normalised_roots)
    suffixes = _normalise_extensions(extensions)
    needle = query.strip().casefold()
    max_entries = max(1, min(int(limit), MAX_LIMIT))

    entries: list[dict[str, object]] = []
    try:
        with os.scandir(current) as iterator:
            for entry in iterator:
                if not show_hidden and entry.name.startswith("."):
                    continue
                if needle and needle not in entry.name.casefold():
                    continue
                try:
                    payload = _entry_payload(
                        Path(entry.path), normalised_roots, mode, suffixes
                    )
                except (OSError, ValueError, OverflowError):
                    # A damaged or out-of-range timestamp must not turn one
                    # entry into a 500 for the whole folder.
                    continue
                if payload is not None:
                    entries.append(payload)
    except PermissionError as exc:
        raise PermissionDeniedError(f"Permission denied while reading: {current}") from exc
    except OSError as exc:
        raise FilesystemError(f"Could not read {current}: {exc}") from exc

    entries.sort(key=lambda item: (item["kind"] != "directory", str(item["name"]).casefold()))
    truncated = len(entries) > max_entries
    return {
        "path": str(current),
        "name": current.name or str(current),
        "parent": _parent_payload(current, normalised_roots),
        "breadcrumbs": _breadcrumbs(current, normalised_roots),
        "roots": roots_payload(normalised_roots),
        "entries": entries[:max_entries],
        "truncated": truncated,
        "can_write": _writable(current),
        "mode": mode,
    }


def create_directory(
    parent: str | Path,
    name: str,
    *,
    roots: Sequence[Path] | None = None,
) -> dict[str, object]:
    """Create one child directory and return it in the same shape as a listing entry."""

    normalised_roots = _normalise_roots(roots)
    parent_path = _resolve_directory(parent, normalised_roots)
    clean_name = validate_directory_name(name)
    target = parent_path / clean_name
    resolve_allowed(target, normalised_roots)
    if target.exists():
        raise DirectoryExistsError(str(target))
    try:
        target.mkdir()
    except FileExistsError as exc:
        raise DirectoryExistsError(str(target)) from exc
    except PermissionError as exc:
        raise PermissionDeniedError(f"Permission denied while creating: {target}") from exc
    except OSError as exc:
        raise FilesystemError(f"Could not create {target}: {exc}") from exc
    resolved = resolve_allowed(target, normalised_roots)
    try:
        stat = resolved.stat()
    except OSError as exc:
        raise FilesystemError(f"Could not inspect {resolved}: {exc}") from exc
    return {
        "name": resolved.name,
        "path": str(resolved),
        "kind": "directory",
        "size_bytes": None,
        "modified_at": _modified_at(stat.st_mtime),
        "extension": None,
        "selectable": True,
        "is_symlink": resolved.is_symlink(),
    }


def validate_directory_name(name: str) -> str:
    """Validate one portable directory segment shared by Linux, macOS, and Windows."""

    clean = name.strip()
    if not clean or clean in {".", ".."}:
        raise InvalidDirectoryNameError("Directory name must not be empty or dot-only.")
    if "/" in clean or "\\" in clean:
        raise InvalidDirectoryNameError("Directory name must not contain a path separator.")
    if any(ord(character) < 32 for character in clean):
        raise InvalidDirectoryNameError("Directory name must not contain control characters.")
    if clean.endswith(" ") or clean.endswith("."):
        raise InvalidDirectoryNameError("Directory name must not end with a space or dot.")
    if any(character in '<>:"|?*' for character in clean):
        raise InvalidDirectoryNameError('Directory name must not contain < > : " | ? or *.')
    stem = clean.split(".", 1)[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        raise InvalidDirectoryNameError(f"Directory name is reserved on Windows: {clean}")
    return clean


def _normalise_roots(roots: Sequence[Path] | None) -> list[Path]:
    source = list(roots) if roots is not None else allowed_roots()
    unique: list[Path] = []
    seen: set[Path] = set()
    for item in source:
        resolved = Path(item).expanduser().resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def _resolve_directory(path: str | Path | None, roots: Sequence[Path]) -> Path:
    if path is None or not str(path).strip():
        for root in roots:
            if root.is_dir():
                return resolve_allowed(root, roots)
        raise PathNotFoundError("No allowed directory is available.")
    candidate = Path(str(path)).expanduser()
    resolved = resolve_allowed(candidate, roots)
    if not resolved.exists():
        raise PathNotFoundError(str(resolved))
    if not resolved.is_dir():
        raise PathNotDirectoryError(str(resolved))
    return resolved


def _entry_payload(
    path: Path,
    roots: Sequence[Path],
    mode: FileMode,
    suffixes: tuple[str, ...],
) -> dict[str, object] | None:
    try:
        resolved = resolve_allowed(path, roots)
        stat = resolved.stat()
    except (PathJailError, OSError, ValueError, OverflowError):
        return None
    is_directory = resolved.is_dir()
    is_file = resolved.is_file()
    if not is_directory and not is_file:
        return None
    if mode == "directory" and not is_directory:
        return None
    suffix = resolved.suffix.lower()
    if is_file and suffixes and suffix not in suffixes:
        return None
    return {
        "name": path.name,
        "path": str(path),
        "kind": "directory" if is_directory else "file",
        "size_bytes": None if is_directory else stat.st_size,
        "modified_at": _modified_at(stat.st_mtime),
        "extension": None if is_directory else suffix or None,
        "selectable": is_directory or mode == "file",
        "is_symlink": path.is_symlink(),
    }


def _normalise_extensions(values: Sequence[str]) -> tuple[str, ...]:
    normalised: list[str] = []
    for value in values:
        item = str(value).strip().lower()
        if not item:
            continue
        if not item.startswith("."):
            item = f".{item}"
        if item not in normalised:
            normalised.append(item)
    return tuple(normalised)


def _parent_payload(path: Path, roots: Sequence[Path]) -> dict[str, str] | None:
    parent = path.parent
    if parent == path:
        return None
    try:
        resolved = resolve_allowed(parent, roots)
    except PathJailError:
        return None
    return {"name": resolved.name or str(resolved), "path": str(resolved)}


def _breadcrumbs(path: Path, roots: Sequence[Path]) -> list[dict[str, str]]:
    containing = [root for root in roots if path == root or path.is_relative_to(root)]
    if not containing:
        return [{"name": path.name or str(path), "path": str(path)}]
    root = max(containing, key=lambda item: len(item.parts))
    crumbs = [{"name": _root_label(root), "path": str(root)}]
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        crumbs.append({"name": part, "path": str(current)})
    return crumbs


def _root_label(root: Path) -> str:
    home = Path.home().resolve(strict=False)
    try:
        cwd = Path.cwd().resolve(strict=False)
    except OSError:
        cwd = None
    portable = portable_home().resolve(strict=False)
    if root == home:
        return "Home"
    if cwd is not None and root == cwd:
        return "Current folder"
    if root == portable:
        return "VideoFlow data"
    return root.name or str(root)


def _writable(path: Path) -> bool:
    try:
        return path.is_dir() and os.access(path, os.W_OK)
    except OSError:
        return False


def _modified_at(timestamp: float) -> str:
    try:
        return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()
    except (OSError, OverflowError, ValueError):
        return datetime(1970, 1, 1, tzinfo=UTC).isoformat()
