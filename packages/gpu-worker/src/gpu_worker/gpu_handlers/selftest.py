"""Trivial end-to-end worker execution probe."""

from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gpu_worker import __version__
from gpu_worker.handlers import Handler

if TYPE_CHECKING:
    from gpu_worker.settings import Settings


def make_selftest_handler(settings: Settings) -> Handler:
    """Return a handler that proves the queue and artifact path work."""

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        target = work_dir / "selftest.json"
        target.write_text(
            json.dumps(
                {
                    "ok": True,
                    "version": __version__,
                    "python": sys.version.split()[0],
                    "platform": platform.platform(),
                    "work_dir": str(settings.work_dir),
                    "inputs": len(input_paths),
                    "at": time.time(),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return [target]

    return handler


__all__ = ["make_selftest_handler"]
