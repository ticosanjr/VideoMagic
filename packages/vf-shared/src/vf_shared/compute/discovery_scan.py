"""Subnet scans and worker probes for LAN discovery."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .discovery_common import _merge_workers

_SCAN_CACHE: dict[tuple[object, ...], tuple[float, list[dict[str, Any]]]] = {}
_SCAN_LOCK = threading.RLock()
_SCAN_TTL_SEC = 15.0
_SUBNET_CACHE: tuple[float, list[str]] = (0.0, [])


def _local_ipv4() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            return str(probe.getsockname()[0])
    except OSError:
        return ""


def local_ipv4_addresses() -> list[str]:
    """Return every usable local IPv4 address, best-effort."""

    addresses: set[str] = set()
    preferred = _local_ipv4()
    if preferred and not preferred.startswith("127."):
        addresses.add(preferred)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = str(info[4][0])
            if not address.startswith("127."):
                addresses.add(address)
    except OSError:
        pass
    return sorted(addresses)


def _subnet_from_command() -> list[str]:
    try:
        if os.name == "nt":
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-NetIPAddress -AddressFamily IPv4 | "
                    "Select-Object IPAddress,PrefixLength | ConvertTo-Json -Compress",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            payload = json.loads(completed.stdout or "[]")
            rows = payload if isinstance(payload, list) else [payload]
            return [
                f"{row['IPAddress']}/{row['PrefixLength']}"
                for row in rows
                if isinstance(row, dict) and row.get("IPAddress")
            ]
        completed = subprocess.run(
            ["ip", "-o", "-4", "addr", "show"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        return [
            f"{match.group(1)}/{match.group(2)}"
            for match in re.finditer(
                r"inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", completed.stdout or ""
            )
        ]
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def local_subnets(*, force: bool = False) -> list[str]:
    """Return private CIDRs for the local interfaces, with a short cache."""

    global _SUBNET_CACHE
    now = time.time()
    if not force and _SUBNET_CACHE[0] and now - _SUBNET_CACHE[0] < 300.0:
        return list(_SUBNET_CACHE[1])
    configured = [
        item.strip()
        for item in os.environ.get("VF_GPU_SCAN_CIDRS", "").split(",")
        if item.strip()
    ]
    candidates = configured or _subnet_from_command()
    if not candidates:
        candidates = [f"{address}/24" for address in local_ipv4_addresses()]
    networks: list[str] = []
    for candidate in candidates:
        try:
            network = ipaddress.ip_network(candidate, strict=False)
        except ValueError:
            continue
        if network.version != 4 or not network.is_private:
            continue
        text = network.compressed
        if text not in networks:
            networks.append(text)
    _SUBNET_CACHE = (now, networks)
    return networks


def _probe_worker(address: str, port: int, timeout: float) -> dict[str, Any] | None:
    import json
    import urllib.request

    url = f"http://{address}:{port}"
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=timeout) as response:
            if response.status != 200:
                return None
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - scan is best-effort
        return None
    if not isinstance(payload, dict) or not payload.get("available", True):
        return None
    worker_id = str(payload.get("worker_id") or "")
    if not worker_id:
        return None
    return {
        "worker_id": worker_id,
        "hostname": str(payload.get("hostname") or ""),
        "ip_local": address,
        "port": int(payload.get("port") or port),
        "url": url,
        "gpu_name": str(payload.get("gpu_name") or ""),
        "vram_total_mb": int(payload.get("vram_total_mb") or 0),
        "vram_free_mb": int(payload.get("vram_free_mb") or 0),
        "status": str(payload.get("status") or ""),
        "queue_depth": int(payload.get("queue_depth") or 0),
        "capabilities": [str(item) for item in payload.get("capabilities") or []],
        "version": str(payload.get("version") or ""),
        "auth_mode": str(payload.get("auth_mode") or ""),
        "nvenc": bool(payload.get("nvenc")),
        "encoder": str(payload.get("encoder") or ""),
        "seen_at": time.time(),
        "transport": "tcp_scan",
    }


def scan_workers(
    *,
    port: int = 8766,
    timeout: float = 0.12,
    max_workers: int = 32,
    cidrs: list[str] | None = None,
    max_hosts: int = 1024,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Probe local subnets when UDP/mDNS discovery is blocked."""

    networks = cidrs or local_subnets()
    if not networks:
        return []
    own = set(local_ipv4_addresses())
    addresses: list[str] = []
    seen: set[str] = set()
    for text in networks:
        try:
            network = ipaddress.ip_network(text, strict=False)
        except ValueError:
            continue
        if network.version != 4:
            continue
        for address in network.hosts():
            value = str(address)
            if value in seen or value in own:
                continue
            seen.add(value)
            addresses.append(value)
            if len(addresses) >= max(1, min(int(max_hosts), 4096)):
                break
        if len(addresses) >= max(1, min(int(max_hosts), 4096)):
            break
    if not addresses:
        return []
    key = (tuple(networks), int(port), tuple(addresses))
    now = time.time()
    if use_cache:
        with _SCAN_LOCK:
            cached = _SCAN_CACHE.get(key)
            if cached is not None and now - cached[0] < _SCAN_TTL_SEC:
                return [dict(item) for item in cached[1]]


    found: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(int(max_workers), 64))) as pool:
        for item in pool.map(lambda address: _probe_worker(address, port, timeout), addresses):
            if item is not None:
                found.append(item)
    merged = _merge_workers(found)
    with _SCAN_LOCK:
        _SCAN_CACHE[key] = (now, merged)
    return [dict(item) for item in merged]
