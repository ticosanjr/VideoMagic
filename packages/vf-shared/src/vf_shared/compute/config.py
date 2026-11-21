"""Cross-process GPU worker configuration.

The controller, the core MCP server, and the domain MCP servers are separate
processes. Environment variables are not enough because OpenCode may start the
servers before the UI pairs a worker. A small ``gpu.json`` file in the
VideoFlow home is the shared source of truth; explicit environment variables
still win.
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

COMPUTE_MODES = ("auto", "local_only", "remote_preferred")
TRANSPORT_MODES = ("auto", "http", "shared")
CONFIG_NAME = "gpu.json"


@dataclass(frozen=True, slots=True)
class GpuConfig:
    mode: str = "auto"
    worker_url: str = ""
    token: str = ""
    worker_id: str = ""
    transport: str = "auto"
    source: str = "default"

    def to_dict(self, *, include_token: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mode": self.mode,
            "worker_url": self.worker_url,
            "worker_id": self.worker_id,
            "transport": self.transport,
            "source": self.source,
        }
        if include_token:
            payload["token"] = self.token
        return payload


def videoflow_home() -> Path:
    override = os.environ.get("VIDEOWFLOW_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".videoflow"


def config_path() -> Path:
    return videoflow_home() / CONFIG_NAME


def _read_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_mode(value: str, default: str = "auto") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in COMPUTE_MODES else default


def _normalize_transport(value: str, default: str = "auto") -> str:
    transport = str(value or "").strip().lower()
    return transport if transport in TRANSPORT_MODES else default


def load_gpu_config() -> GpuConfig:
    """Resolve GPU settings from env, then ``gpu.json``, then defaults."""

    path = config_path()
    file_payload = _read_file(path)
    env_url = os.environ.get("VF_GPU_WORKER_URL", "").strip()
    env_token = os.environ.get("VF_GPU_WORKER_TOKEN", "").strip()
    env_mode = os.environ.get("VF_COMPUTE_MODE", "").strip()
    env_worker = os.environ.get("VF_GPU_WORKER_ID", "").strip()
    env_transport = os.environ.get("VF_GPU_TRANSPORT", "").strip()
    worker_url = env_url or str(file_payload.get("worker_url") or "").strip()
    token = env_token or str(file_payload.get("token") or "").strip()
    mode = _normalize_mode(
        env_mode or str(file_payload.get("mode") or "auto"),
    )
    transport = _normalize_transport(
        env_transport or str(file_payload.get("transport") or "auto"),
    )
    worker_id = env_worker or str(file_payload.get("worker_id") or "").strip()
    if env_url or env_token or env_mode or env_worker or env_transport:
        source = "env"
    elif file_payload:
        source = str(path)
    else:
        source = "default"
    return GpuConfig(
        mode=mode,
        worker_url=worker_url.rstrip("/"),
        token=token,
        worker_id=worker_id,
        transport=transport,
        source=source,
    )


def save_gpu_config(
    *,
    mode: str = "auto",
    worker_url: str = "",
    token: str = "",
    worker_id: str = "",
    transport: str = "auto",
) -> Path:
    """Persist the shared GPU configuration atomically."""

    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": 1,
        "mode": _normalize_mode(mode),
        "worker_url": str(worker_url or "").strip().rstrip("/"),
        "token": str(token or "").strip(),
        "worker_id": str(worker_id or "").strip(),
        "transport": _normalize_transport(transport),
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)
    return path


def clear_gpu_config() -> None:
    config_path().unlink(missing_ok=True)


__all__ = [
    "COMPUTE_MODES",
    "CONFIG_NAME",
    "GpuConfig",
    "TRANSPORT_MODES",
    "clear_gpu_config",
    "config_path",
    "load_gpu_config",
    "save_gpu_config",
    "videoflow_home",
]
