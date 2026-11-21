"""Detect and repair a broken ONNX Runtime installation.

``faster-whisper`` and ``rembg`` install the CPU ``onnxruntime`` distribution
while the Windows kit also installs ``onnxruntime-gpu``. Both own the same
``site-packages/onnxruntime`` directory. Uninstalling only one leaves a partial
module that imports but lacks ``SessionOptions``; Silero VAD then fails at the
first transcription.

This module performs the repair explicitly: uninstall both distributions,
remove leftovers, force-reinstall the GPU wheel, and verify the deep API.
"""

from __future__ import annotations

import argparse
import json
import shutil
import site
import subprocess
import sys
import sysconfig
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

Runner = Callable[..., subprocess.CompletedProcess[str]]
ONNX_PACKAGE = "onnxruntime-gpu==1.20.2"


def onnx_status() -> dict[str, Any]:
    """Return the deep ONNX status without importing at module load."""

    try:
        import onnxruntime as ort  # noqa: PLC0415 - optional dependency
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "version": "",
            "providers": [],
            "error": f"{type(exc).__name__}: {exc}",
        }
    version = str(getattr(ort, "__version__", "") or "")
    options = getattr(ort, "SessionOptions", None)
    session = getattr(ort, "InferenceSession", None)
    if options is None or session is None:
        missing = "SessionOptions" if options is None else "InferenceSession"
        return {
            "ok": False,
            "version": version,
            "providers": [],
            "error": (
                f"AttributeError: module 'onnxruntime' has no attribute '{missing}'"
            ),
        }
    try:
        options()
        providers = [str(item) for item in ort.get_available_providers()]
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "version": version,
            "providers": [],
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {"ok": True, "version": version, "providers": providers, "error": ""}


def _purelib() -> Path:
    try:
        return Path(sysconfig.get_paths()["purelib"])
    except (KeyError, OSError):
        return Path(site.getsitepackages()[0])


def _purge_leftovers(purelib: Path) -> list[str]:
    removed: list[str] = []
    for pattern in ("onnxruntime", "onnxruntime-*", "onnxruntime_gpu-*"):
        for path in purelib.glob(pattern):
            if path.is_dir() and path.name == "onnxruntime" or path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
            removed.append(str(path))
    return removed


def _base_command(uv: str | None) -> list[str]:
    if uv:
        return [uv, "pip"]
    return [sys.executable, "-m", "pip"]


def repair_onnx(
    *,
    uv: str | None = None,
    runner: Runner = subprocess.run,
    python: str | None = None,
    purelib: Path | None = None,
) -> dict[str, Any]:
    """Force a clean GPU ONNX install and verify the deep API."""

    target_python = python or sys.executable
    base = _base_command(uv)
    pip = ["--python", target_python] if uv else []
    commands: list[list[str]] = []
    outputs: list[str] = []

    def run(args: Sequence[str]) -> int:
        commands.append(list(args))
        completed = runner(
            list(args),
            capture_output=True,
            text=True,
            check=False,
            timeout=900,
        )
        text = (completed.stderr or completed.stdout or "").strip()
        if text:
            outputs.append(text[-800:])
        return int(completed.returncode)

    run([*base, "uninstall", *pip, "-y", "onnxruntime", "onnxruntime-gpu"])
    removed = _purge_leftovers(purelib or _purelib())
    run(
        [
            *base,
            "install",
            *pip,
            "--force-reinstall",
            "--no-deps",
            ONNX_PACKAGE,
        ]
    )
    status = onnx_status()
    if not status["ok"]:
        run(
            [
                *base,
                "install",
                *pip,
                "--force-reinstall",
                "--no-deps",
                "--no-cache-dir",
                ONNX_PACKAGE,
            ]
        )
        status = onnx_status()
    return {
        "ok": bool(status["ok"]),
        "status": status,
        "commands": commands,
        "removed": removed,
        "output_tail": outputs[-3:],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Only report status.")
    parser.add_argument("--fix", action="store_true", help="Repair ONNX Runtime.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    parser.add_argument("--uv", default="", help="Path to uv.exe (optional).")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.check and not args.fix:
        status = onnx_status()
        payload: dict[str, Any] = {"ok": status["ok"], "status": status}
        print(json.dumps(payload, indent=2) if args.json else status)
        return 0 if status["ok"] else 1

    result = repair_onnx(uv=args.uv or None)
    print(json.dumps(result, indent=2) if args.json else result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "onnx_status", "repair_onnx"]
