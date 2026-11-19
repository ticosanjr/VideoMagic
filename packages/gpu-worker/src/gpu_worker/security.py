"""Path and identifier validation shared by the HTTP layer and the worker."""

from __future__ import annotations

import re
from pathlib import Path

ARTIFACT_ID_RE = re.compile(r"^[0-9a-f]{64}$")
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
CAPABILITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_EXTENSION_RE = re.compile(r"^\.[a-z0-9]{1,10}$")


class UnsafePathError(ValueError):
    """Raised when a path or identifier could escape its allowed root."""


def is_artifact_id(value: object) -> bool:
    return isinstance(value, str) and ARTIFACT_ID_RE.fullmatch(value) is not None


def is_job_id(value: object) -> bool:
    return isinstance(value, str) and JOB_ID_RE.fullmatch(value) is not None


def is_capability(value: object) -> bool:
    return isinstance(value, str) and CAPABILITY_RE.fullmatch(value) is not None


def safe_filename(value: str | None, *, default: str = "upload") -> str:
    """Return a single safe path component, never a directory traversal."""

    raw = (value or "").replace("\\", "/").strip()
    name = Path(raw).name.strip()
    if not name or name in {".", ".."}:
        return default
    if "\x00" in name:
        raise UnsafePathError("filename contains a null byte")
    return name[:255]


def safe_extension(value: str | None) -> str:
    """Return a conservative lowercase extension or ``.bin``."""

    if not value:
        return ".bin"
    suffix = Path(value.replace("\\", "/")).suffix.lower()
    return suffix if _EXTENSION_RE.fullmatch(suffix) else ".bin"


def unique_path(directory: Path, name: str) -> Path:
    """Return a non-existing path inside ``directory`` with a safe basename."""

    candidate = directory / safe_filename(name)
    if not candidate.exists():
        return candidate
    for index in range(1, 10_000):
        alternative = directory / f"{candidate.stem}-{index}{candidate.suffix}"
        if not alternative.exists():
            return alternative
    raise UnsafePathError("could not allocate a unique output filename")


def resolve_shared_path(root: Path, relative: str) -> Path:
    """Resolve a read-only shared input inside ``root``.

    Rejects absolute paths, traversal, null bytes, and symlinks that resolve outside the
    shared root. The returned path is guaranteed to be an existing regular file.
    """

    if not isinstance(relative, str) or not relative.strip():
        raise UnsafePathError("shared input path must be a non-empty string")
    if "\x00" in relative or "\\" in relative:
        raise UnsafePathError("shared input path contains an invalid character")
    candidate = Path(relative)
    if candidate.is_absolute() or candidate.anchor:
        raise UnsafePathError("shared input path must be relative")
    if any(part == ".." for part in candidate.parts):
        raise UnsafePathError("shared input path may not contain '..'")

    root_resolved = root.expanduser().resolve()
    resolved = (root_resolved / candidate).resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise UnsafePathError("shared input path escapes the shared root")
    if not resolved.is_file():
        raise UnsafePathError("shared input path is not a file")
    return resolved


def resolve_shared_output(root: Path, relative: str) -> Path:
    """Resolve a write target inside ``root``.

    The parent directory must already exist so the worker cannot create arbitrary
    directory trees. Existing symlinks are resolved and must stay inside the root.
    """

    if not isinstance(relative, str) or not relative.strip():
        raise UnsafePathError("shared output path must be a non-empty string")
    if "\x00" in relative or "\\" in relative:
        raise UnsafePathError("shared output path contains an invalid character")
    candidate = Path(relative)
    if candidate.is_absolute() or candidate.anchor:
        raise UnsafePathError("shared output path must be relative")
    if any(part == ".." for part in candidate.parts):
        raise UnsafePathError("shared output path may not contain '..'")
    if candidate.name in {"", ".", ".."}:
        raise UnsafePathError("shared output path must name a file")

    root_resolved = root.expanduser().resolve()
    parent = (root_resolved / candidate).parent.resolve()
    if parent != root_resolved and root_resolved not in parent.parents:
        raise UnsafePathError("shared output path escapes the shared root")
    if not parent.is_dir():
        raise UnsafePathError("shared output parent directory does not exist")
    return parent / candidate.name
