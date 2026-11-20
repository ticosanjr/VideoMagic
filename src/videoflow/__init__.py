"""VideoFlow core package.

Implemented: rational time, state, cache, planning, retake guard, FFmpeg ingest,
speech detection, SRT, local Faster-Whisper and whisper.cpp transcription,
deterministic timeline construction, three NLE exporters, jobs, the live API,
the rack UI, Silero VAD, and the MCP surface.
"""

from __future__ import annotations

import importlib.abc
import importlib.util
import sys
from pathlib import Path

__version__ = "3.16.0"


class _OverlayFinder(importlib.abc.MetaPathFinder):
    """Load ``videoflow`` modules from ``app/videoflow`` when a fast bundle has them."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "videoflow" and not fullname.startswith("videoflow."):
            return None
        parts = tuple(fullname.split("."))
        module = self.root.joinpath(*parts).with_suffix(".py")
        if module.is_file():
            return importlib.util.spec_from_file_location(fullname, module)
        package = self.root.joinpath(*parts)
        init = package / "__init__.py"
        if init.is_file():
            return importlib.util.spec_from_file_location(
                fullname,
                init,
                submodule_search_locations=[str(package)],
            )
        return None


def _install_overlay() -> None:
    """Prefer the source overlay shipped beside a fast onedir bundle."""

    if not getattr(sys, "frozen", False):
        return
    overlay = Path(sys.executable).resolve().parent / "app"
    package = overlay / "videoflow"
    if not (package / "__init__.py").is_file():
        return
    sys.meta_path.insert(0, _OverlayFinder(overlay))
    if str(overlay) not in sys.path:
        sys.path.insert(0, str(overlay))
    globals()["__path__"] = [str(package)]
    version_file = overlay / "version.txt"
    if version_file.is_file():
        globals()["__version__"] = version_file.read_text(encoding="utf-8").strip()


_install_overlay()
