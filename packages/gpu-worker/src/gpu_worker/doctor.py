"""Worker dependency doctor.

Optional GPU dependencies fail in different ways: a module can be present but
raise on import (for example CTranslate2 importing ``pkg_resources`` after
setuptools 81 removed it). This module performs real imports and returns a
small, stable report that the bootstrap, ``/health``, and the dashboard can
show without crashing the worker.
"""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gpu_worker.nvenc import probe_nvenc

if TYPE_CHECKING:
    from gpu_worker.settings import Settings

_CACHE: dict[str, Any] = {}


def _import_detail(module: str) -> tuple[bool, str, str]:
    try:
        imported = importlib.import_module(module)
    except Exception as exc:  # noqa: BLE001 - report, never raise
        return False, "", f"{type(exc).__name__}: {exc}"
    version = str(getattr(imported, "__version__", "") or "")
    return True, version, ""


def _model_present(model: str) -> bool:
    name = str(model or "").strip()
    if not name:
        return False
    if Path(name).expanduser().is_dir():
        return True
    cache = Path.home() / ".cache" / "huggingface" / "hub"
    normalized = name.replace("/", "--")
    return any(
        path.is_dir()
        for path in (
            cache / f"models--Systran--faster-whisper-{normalized}",
            cache / f"models--Systran--faster-whisper-{name}",
            cache / f"models--{normalized}",
        )
    )


def dependency_report(settings: Settings, *, force: bool = False) -> dict[str, Any]:
    """Return a cached, real-import report for optional worker dependencies."""

    if _CACHE and not force:
        return dict(_CACHE)
    ffmpeg = settings.ffmpeg_cmd or "ffmpeg"
    ffmpeg_ok = bool(shutil.which(ffmpeg) or Path(ffmpeg).expanduser().is_file())
    pkg_ok, pkg_version, pkg_error = _import_detail("pkg_resources")
    ct2_ok, ct2_version, ct2_error = _import_detail("ctranslate2")
    devices = 0
    if ct2_ok:
        try:
            devices = int(importlib.import_module("ctranslate2").get_cuda_device_count())
        except Exception:  # noqa: BLE001 - optional CUDA state
            devices = 0
    asr_ok, asr_version, asr_error = _import_detail("faster_whisper")
    if asr_ok and ct2_error:
        asr_ok, asr_error = False, ct2_error
    onnx_ok, onnx_version, onnx_error = _import_detail("onnxruntime")
    providers: list[str] = []
    if onnx_ok:
        try:
            providers = [
                str(item)
                for item in importlib.import_module(
                    "onnxruntime"
                ).get_available_providers()
            ]
        except Exception:  # noqa: BLE001 - provider probe is advisory
            providers = []
    nvenc = probe_nvenc(ffmpeg)
    model = str(getattr(settings, "asr_model", "") or "large-v3-turbo")
    model_ready = _model_present(model)
    dependencies = {
        "python": {
            "executable": sys.executable,
            "version": sys.version.split()[0],
        },
        "setuptools": {
            "ok": pkg_ok,
            "version": pkg_version,
            "error": pkg_error,
        },
        "pkg_resources": {
            "ok": pkg_ok,
            "error": pkg_error,
        },
        "ctranslate2": {
            "ok": ct2_ok,
            "version": ct2_version,
            "cuda_devices": devices,
            "error": ct2_error,
        },
        "faster_whisper": {
            "ok": asr_ok,
            "version": asr_version,
            "error": asr_error,
        },
        "onnxruntime": {
            "ok": onnx_ok,
            "version": onnx_version,
            "providers": providers,
            "error": onnx_error,
        },
        "ffmpeg": {
            "ok": ffmpeg_ok,
            "path": shutil.which(ffmpeg) or (ffmpeg if ffmpeg_ok else ""),
        },
        "nvenc": nvenc.to_dict(),
        "asr_model": {
            "name": model,
            "cache_present": model_ready,
        },
    }
    asr_ready = bool(asr_ok and pkg_ok)
    asr_reason = ""
    if not pkg_ok:
        asr_reason = (
            "pkg_resources ausente: instale setuptools<81 "
            f"({pkg_error or 'módulo não encontrado'})"
        )
    elif not asr_ok:
        asr_reason = asr_error or "faster-whisper não importa"
    elif not model_ready:
        asr_reason = (
            f"modelo {model} não está no cache; abra o worker com internet "
            "e execute o warmup para baixá-lo"
        )
    checks = {
        "pkg_resources": pkg_ok,
        "ctranslate2": ct2_ok,
        "faster_whisper": asr_ok,
        "onnxruntime": onnx_ok,
        "ffmpeg": ffmpeg_ok,
        "nvenc": nvenc.available,
    }
    report = {
        "ok": all(checks.values()),
        "checks": checks,
        "asr_ready": asr_ready,
        "asr_error": asr_reason,
        "asr_model_ready": model_ready,
        "dependencies": dependencies,
    }
    _CACHE.clear()
    _CACHE.update(report)
    return dict(report)


def clear_cache() -> None:
    _CACHE.clear()


__all__ = ["clear_cache", "dependency_report"]
