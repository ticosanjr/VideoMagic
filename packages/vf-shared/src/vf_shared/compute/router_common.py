"""Environment, shared-mount and placement helpers for the compute router."""

from __future__ import annotations

import os
import time
from pathlib import Path

from vf_shared.compute.models import WorkerDecision

_DEFAULT_MODE = "auto"


_DEFAULT_HEALTH_TTL = 1.0


_DEFAULT_HEALTH_TIMEOUT = 0.3


_DEFAULT_MIN_VRAM_MB = 2048


_DEFAULT_MAX_QUEUE = 2


_DEFAULT_CIRCUIT_SEC = 2.0


_DEFAULT_DISCOVERY_TIMEOUT = 0.8
_DEFAULT_MAX_UTILIZATION = 70.0


_DISCOVERY_TTL = 5.0


def _env_str(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None else value.strip()


def _env_float(name: str, default: float) -> float:
    raw = _env_str(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = _env_str(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = True) -> bool:
    raw = _env_str(name)
    if not raw:
        return default
    return raw.lower() not in {"0", "false", "no", "off"}


def _valid_shared_file(path: Path) -> bool:
    """Wait briefly for SMB metadata and require a non-empty file."""

    for _attempt in range(3):
        try:
            if path.is_file() and path.stat().st_size > 0:
                return True
        except OSError:
            pass
        time.sleep(0.25)
    return False


def _shared_relative(root: str | Path | None, value: str) -> str:
    """Return ``value`` relative to a local shared mount, or ``""``."""

    if not root:
        return ""
    try:
        base = Path(root).expanduser().resolve()
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            return ""
        return path.relative_to(base).as_posix()
    except (OSError, ValueError):
        return ""


def _local(reason: str, capability: str) -> WorkerDecision:
    return WorkerDecision(
        mode="local",
        reason=reason,
        capability=capability,
        execution_node="local",
    )
