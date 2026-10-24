"""Minimal crash reports with no environment leakage."""

from __future__ import annotations

import json
import platform
import traceback
from datetime import UTC, datetime
from pathlib import Path

from videoflow import __version__
from videoflow.runtime import portable_home


def crash_dir() -> Path:
    directory = portable_home() / "crash-reports"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def write_crash_report(exc: BaseException, *, where: str = "") -> Path:
    """Write a JSON report with the exception and a minimal environment."""

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = crash_dir() / f"crash-{stamp}.json"
    payload = {
        "version": __version__,
        "where": where,
        "type": exc.__class__.__name__,
        "message": str(exc),
        "traceback": "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )[-8000:],
        "python": platform.python_version(),
        "platform": platform.system().lower(),
        "machine": platform.machine(),
    }
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target
