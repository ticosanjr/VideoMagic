"""Disk, log, LAN, and job projections used by the worker HTTP app."""

from __future__ import annotations

import os
import shutil
import socket
from pathlib import Path
from typing import Any

from gpu_worker.settings import Settings
from gpu_worker.store import JobStore


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            return str(probe.getsockname()[0])
    except OSError:
        return "127.0.0.1"


def lan_urls() -> list[str]:
    urls: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            address = str(info[4][0])
            if address.startswith("127.") or address in urls:
                continue
            urls.append(address)
    except OSError:
        pass
    local = local_ip()
    if local and not local.startswith("127.") and local not in urls:
        urls.insert(0, local)
    return urls


def disk_free_mb(path: Path) -> int:
    try:
        return int(shutil.disk_usage(path).free // (1024 * 1024))
    except OSError:
        return 0


def log_path(config: Settings) -> Path:
    explicit = os.environ.get("VF_GPU_LOG_FILE", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    return Path(config.work_dir) / "worker.log"


def tail_log(config: Settings, *, limit: int = 200) -> str:
    path = log_path(config)
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-limit:])


def rotate_log(config: Settings) -> bool:
    path = log_path(config)
    if not path.is_file():
        return False
    limit = max(1, int(config.log_max_mb)) * 1024 * 1024
    try:
        if path.stat().st_size <= limit:
            return False
        os.replace(path, path.with_name(f"{path.name}.1"))
        return True
    except OSError:
        return False


def current_job(store: JobStore) -> dict[str, Any] | None:
    for job in store.list_jobs(limit=10):
        if job.status in {"queued", "running"}:
            return job.summary()
    return None


__all__ = [
    "current_job",
    "disk_free_mb",
    "lan_urls",
    "local_ip",
    "log_path",
    "rotate_log",
    "tail_log",
]
