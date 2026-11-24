"""Detect a usable local NVIDIA CUDA device.

A GPU worker is optional: on a Windows 11 desktop (or any workstation with an
NVIDIA card) VideoFlow should run Faster-Whisper on CUDA and encode with NVENC
locally instead of asking for a remote worker. Detection must stay cheap and
never fail when the optional runtime is missing: ``ctranslate2`` is asked when
it is importable, otherwise ``nvidia-smi`` is used.
"""

from __future__ import annotations

import shutil
import subprocess

_CACHE: dict[str, bool] = {}


def _run_nvidia_smi(*args: str) -> str:
    binary = shutil.which("nvidia-smi")
    if not binary:
        return ""
    try:
        completed = subprocess.run(
            [binary, *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout if completed.returncode == 0 else ""


def cuda_device_count() -> int:
    """Number of CUDA devices seen by CTranslate2 or ``nvidia-smi``."""

    try:
        import ctranslate2  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - optional dependency
        ctranslate2 = None
    if ctranslate2 is not None:
        try:
            return max(0, int(ctranslate2.get_cuda_device_count()))
        except Exception:  # noqa: BLE001 - a broken driver must not crash
            pass
    output = _run_nvidia_smi("-L")
    return sum(1 for line in output.splitlines() if line.strip().startswith("GPU "))


def local_gpu_name() -> str:
    """Best-effort human name for the first local NVIDIA GPU."""

    output = _run_nvidia_smi("--query-gpu=name", "--format=csv,noheader")
    return next((line.strip() for line in output.splitlines() if line.strip()), "")


def local_gpu_available(*, force: bool = False) -> bool:
    """Whether a local NVIDIA CUDA device is present."""

    if not force and "available" in _CACHE:
        return _CACHE["available"]
    available = cuda_device_count() > 0
    _CACHE["available"] = available
    return available


def reset_local_gpu_cache() -> None:
    """Forget the cached detection result (used after a driver change)."""

    _CACHE.clear()


__all__ = [
    "cuda_device_count",
    "local_gpu_available",
    "local_gpu_name",
    "reset_local_gpu_cache",
]
