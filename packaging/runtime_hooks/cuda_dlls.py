"""Expose bundled NVIDIA DLLs before importing CTranslate2/Faster-Whisper."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _add(path: Path) -> None:
    if not path.is_dir():
        return
    try:
        os.add_dll_directory(str(path))
    except (AttributeError, OSError):
        pass
    os.environ["PATH"] = str(path) + os.pathsep + os.environ.get("PATH", "")


if sys.platform == "win32":
    root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    _add(root / "nvidia")
    for candidate in root.glob("nvidia/*/bin"):
        _add(candidate)
    _add(root / "ctranslate2")
