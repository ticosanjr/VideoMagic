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
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        return Path(appimage).expanduser().resolve().parent / "videoflow-data"
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


def find_whisper_binary() -> str | None:
    override = os.environ.get("VIDEOWFLOW_WHISPER_BIN")
    if override:
        return override
    suffix = ".exe" if os.name == "nt" else ""
    candidates = (
        bundle_root() / "whisper" / f"whisper-cli{suffix}",
        bundle_root() / "whisper" / f"main{suffix}",
        executable_dir() / "whisper" / f"whisper-cli{suffix}",
        executable_dir() / f"whisper-cli{suffix}",
        bundle_root() / "vendor" / "whisper" / f"whisper-cli{suffix}",
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def find_whisper_model() -> Path | None:
    override = os.environ.get("VIDEOWFLOW_WHISPER_MODEL")
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None
    candidates = (
        bundle_root() / "whisper" / "ggml-tiny.bin",
        bundle_root() / "vendor" / "whisper" / "ggml-tiny.bin",
        executable_dir() / "whisper" / "ggml-tiny.bin",
        executable_dir() / "ggml-tiny.bin",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def find_silero_model() -> Path | None:
    override = os.environ.get("VIDEOWFLOW_SILERO_MODEL")
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None
    candidates = (
        bundle_root() / "silero" / "silero_vad.onnx",
        bundle_root() / "vendor" / "silero" / "silero_vad.onnx",
        executable_dir() / "silero" / "silero_vad.onnx",
        executable_dir() / "silero_vad.onnx",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


FASTER_WHISPER_MODEL_MB = {
    "tiny": 75,
    "base": 145,
    "small": 484,
    "medium": 1530,
    "large-v3": 3090,
}


def find_faster_whisper_model(model_size: str = "small") -> Path | None:
    """Resolve a local CTranslate2 model directory; never download one."""

    override = os.environ.get("VIDEOWFLOW_FASTER_WHISPER_MODEL")
    if override:
        path = Path(override).expanduser()
        return path if _is_faster_whisper_model(path) else None
    for candidate in _faster_whisper_candidates(model_size):
        if _is_faster_whisper_model(candidate):
            return candidate
    return None


def expected_faster_whisper_model(model_size: str = "small") -> Path:
    """Return the path an operator should populate when the model is missing."""

    override = os.environ.get("VIDEOWFLOW_FASTER_WHISPER_MODEL")
    if override:
        return Path(override).expanduser()
    if not is_frozen():
        return bundle_root() / "vendor" / "faster-whisper" / model_size
    return bundle_root() / "faster-whisper" / model_size


def _faster_whisper_candidates(model_size: str) -> tuple[Path, ...]:
    return (
        bundle_root() / "faster-whisper" / model_size,
        bundle_root() / "vendor" / "faster-whisper" / model_size,
        executable_dir() / "faster-whisper" / model_size,
        executable_dir() / "vendor" / "faster-whisper" / model_size,
        portable_home() / "models" / "faster-whisper" / model_size,
    )


def _is_faster_whisper_model(path: Path) -> bool:
    return path.is_dir() and (path / "model.bin").is_file() and (path / "config.json").is_file()


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
