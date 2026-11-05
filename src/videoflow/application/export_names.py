"""Unique export names derived from the source video and a timestamp."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

_UNSAFE = re.compile(r"[^0-9A-Za-zÀ-ÿ._-]+")
_KNOWN_SUFFIXES = (".fcpxml", ".xml", ".kdenlive", ".mp4")


def safe_stem(source: Path | str) -> str:
    """Return a filesystem-safe stem for the source video."""

    stem = Path(source).stem.strip()
    stem = _UNSAFE.sub("_", stem).strip("._-")
    return stem or "video"


def timestamped_basename(
    source: Path | str,
    *,
    now: datetime | None = None,
) -> str:
    """Return ``<source>_VideoFlow_Edited_<yymmddhhmmss>``."""

    stamp = (now or datetime.now()).strftime("%y%m%d%H%M%S")
    return f"{safe_stem(source)}_VideoFlow_Edited_{stamp}"


def unique_basename(
    directory: Path,
    base: str,
    suffixes: Sequence[str],
) -> str:
    """Append ``_1``, ``_2`` until no target suffix exists in ``directory``."""

    candidate = base
    index = 1
    while any(
        (Path(directory) / f"{candidate}{suffix}").exists()
        for suffix in suffixes
    ):
        candidate = f"{base}_{index}"
        index += 1
    return candidate


def unique_path(directory: Path, filename: str) -> Path:
    """Return a path that does not overwrite an existing file."""

    path = Path(directory) / filename
    if not path.exists():
        return path
    index = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def fixed_basename(value: str) -> str:
    """Normalise a user-supplied fixed base name."""

    name = Path(value).name.strip()
    lowered = name.casefold()
    for suffix in _KNOWN_SUFFIXES:
        if lowered.endswith(suffix):
            name = name[: -len(suffix)]
            break
    name = _UNSAFE.sub("_", name).strip("._-")
    return name or "timeline"
