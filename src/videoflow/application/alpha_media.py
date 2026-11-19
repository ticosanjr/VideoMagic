"""Native alpha-media handling for overlays and NLE delivery.

FFmpeg's default VP9 decoder discards the alpha plane. MP4 composition forces
``libvpx-vp9``; NLEs get an optional cached ProRes 4444 conversion because most
editors do not read VP9 alpha reliably.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from videoflow.runtime import cache_root, find_binary

__all__ = [
    "alpha_input_args",
    "is_alpha_video",
    "prepare_prores_overlay",
]

_ALPHA_SUFFIXES = {".webm", ".mov"}


def is_alpha_video(path: Path) -> bool:
    return Path(path).suffix.casefold() in _ALPHA_SUFFIXES


def alpha_input_args(path: Path) -> list[str]:
    """Decoder flags that preserve the alpha plane for one input path."""

    suffix = Path(path).suffix.casefold()
    if suffix == ".webm":
        return ["-c:v", "libvpx-vp9"]
    return []


def _digest(path: Path) -> str:
    stat = path.stat()
    payload = f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}".encode()
    return hashlib.sha256(payload).hexdigest()[:24]


def prepare_prores_overlay(path: Path, *, cache_dir: Path | None = None) -> Path:
    """Return a ProRes 4444 copy of a WebM overlay, cached by source identity.

    Non-WebM inputs and unavailable FFmpeg return the original path so callers
    still get a usable export instead of a hard failure.
    """

    source = Path(path).expanduser()
    if source.suffix.casefold() != ".webm" or not source.is_file():
        return source
    binary = find_binary("ffmpeg")
    if binary is None:
        return source
    root = Path(cache_dir).expanduser() if cache_dir is not None else cache_root() / "alpha"
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{source.stem}-{_digest(source)}-4444.mov"
    if target.is_file() and target.stat().st_size > 0:
        return target
    completed = subprocess.run(
        [
            binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-c:v",
            "libvpx-vp9",
            "-i",
            str(source),
            "-c:v",
            "prores_ks",
            "-profile:v",
            "4444",
            "-pix_fmt",
            "yuva444p10le",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not target.is_file():
        target.unlink(missing_ok=True)
        return source
    return target
