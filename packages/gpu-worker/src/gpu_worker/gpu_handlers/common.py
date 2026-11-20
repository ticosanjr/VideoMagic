"""Shared FFmpeg and NVENC helpers for built-in GPU handlers."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from gpu_worker.handlers import HandlerError

if TYPE_CHECKING:
    from gpu_worker.settings import Settings

_NVENC_CACHE: dict[str, bool] = {}
_NVENC_REASONS: dict[str, str] = {}

def _available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _ffmpeg(settings: Settings) -> str:
    return settings.ffmpeg_cmd or os.environ.get("VF_GPU_FFMPEG") or "ffmpeg"


def _escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _run(tokens: list[str], *, timeout: float = 3600.0) -> None:
    try:
        completed = subprocess.run(
            tokens,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise HandlerError(f"command not found: {tokens[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise HandlerError(f"command timed out after {timeout:.0f}s") from exc
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()
        raise HandlerError(
            f"command exited with status {completed.returncode}: "
            f"{tail[-1][:300] if tail else 'no stderr'}"
        )


def nvenc_available(ffmpeg: str = "ffmpeg") -> bool:
    """Return whether FFmpeg exposes ``h264_nvenc``."""

    key = str(ffmpeg)
    cached = _NVENC_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        completed = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if completed.returncode != 0 or "h264_nvenc" not in completed.stdout:
            _NVENC_CACHE[key] = False
            return False
        probe = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=128x72:d=0.1",
                "-c:v",
                "h264_nvenc",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        _NVENC_CACHE[key] = False
        _NVENC_REASONS[key] = str(exc)[-500:]
        return False
    available = probe.returncode == 0
    _NVENC_CACHE[key] = available
    _NVENC_REASONS[key] = "" if available else (
        (probe.stderr or probe.stdout or "h264_nvenc probe failed").strip()[-500:]
    )
    return available


def nvenc_error(ffmpeg: str = "ffmpeg") -> str:
    nvenc_available(ffmpeg)
    return _NVENC_REASONS.get(str(ffmpeg), "")


def _binary_available(binary: str) -> bool:
    candidate = shutil.which(binary)
    if candidate:
        return True
    return Path(binary).expanduser().is_file()


def _run_in(tokens: list[str], cwd: Path, *, timeout: float = 3600.0) -> None:
    try:
        completed = subprocess.run(
            tokens,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise HandlerError(f"command not found: {tokens[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise HandlerError(f"command timed out after {timeout:.0f}s") from exc
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()
        raise HandlerError(
            f"command exited with status {completed.returncode}: "
            f"{tail[-1][:300] if tail else 'no stderr'}"
        )
