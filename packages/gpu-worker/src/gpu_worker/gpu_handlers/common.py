"""Shared FFmpeg and NVENC helpers for built-in GPU handlers."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from gpu_worker.handlers import HandlerError
from gpu_worker.nvenc import (  # noqa: F401 - historical import surface
    _NVENC_CACHE,
    _NVENC_PROBES,
    _NVENC_REASONS,
    NvencProbe,
    nvenc_advice,
    nvenc_args,
    nvenc_available,
    nvenc_error,
    probe_nvenc,
)

if TYPE_CHECKING:
    from gpu_worker.settings import Settings


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
