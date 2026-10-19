"""Portable runtime locations.

A frozen onefile build keeps its data next to the executable, so the whole app can
live on a USB stick. A development checkout keeps data in ``~/.videoflow``.
Environment overrides exist for both.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Directory that holds bundled data and binaries."""

    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]


def executable_dir() -> Path:
    return Path(sys.executable).resolve().parent


def portable_home() -> Path:
    override = os.environ.get("VIDEOWFLOW_HOME")
    if override:
        return Path(override).expanduser()
    if is_frozen():
        return executable_dir() / "videoflow-data"
    return Path.home() / ".videoflow"


def ensure_home() -> Path:
    home = portable_home()
    home.mkdir(parents=True, exist_ok=True)
    return home


def find_binary(name: str) -> str | None:
    """Resolve a bundled or system binary, honouring ``VIDEOWFLOW_<NAME>``."""

    override = os.environ.get(f"VIDEOWFLOW_{name.upper()}")
    if override:
        return override
    suffix = ".exe" if os.name == "nt" else ""
    candidates = (
        bundle_root() / "vendor" / f"{name}{suffix}",
        bundle_root() / f"{name}{suffix}",
        executable_dir() / f"{name}{suffix}",
        executable_dir() / "vendor" / f"{name}{suffix}",
        executable_dir() / "ffmpeg" / "bin" / f"{name}{suffix}",
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


def allowed_roots() -> list[Path]:
    """Directories the HTTP and MCP surfaces may read or write.

    ``VIDEOWFLOW_ALLOWED_ROOTS`` is a path-separator list. Without it, the user's
    home, the current directory, and the portable data directory are allowed.
    """

    raw = os.environ.get("VIDEOWFLOW_ALLOWED_ROOTS", "")
    roots = [Path(item).expanduser() for item in raw.split(os.pathsep) if item]
    if roots:
        return roots
    return [Path.home(), Path.cwd(), portable_home()]


def ui_dir() -> Path | None:
    override = os.environ.get("VIDEOWFLOW_UI_DIR")
    candidates = [Path(override).expanduser()] if override else []
    candidates.extend(
        (
            bundle_root() / "ui",
            Path(__file__).resolve().parents[2] / "ui" / "build",
        )
    )
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None
