"""LAN discovery of GPU workers through UDP broadcast beacons."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any

DEFAULT_DISCOVERY_PORT = 8767
DEFAULT_PEER_TTL_SEC = 10.0
_SCAN_CACHE: dict[tuple[object, ...], tuple[float, list[dict[str, Any]]]] = {}
_SCAN_LOCK = threading.RLock()
_SCAN_TTL_SEC = 15.0
_SUBNET_CACHE: tuple[float, list[str]] = (0.0, [])


@dataclass(slots=True)
class DiscoveredWorker:
    worker_id: str
    hostname: str = ""
    ip_local: str = ""
    port: int = 0
    gpu_name: str = ""
    vram_total_mb: int = 0
    vram_free_mb: int = 0
    status: str = ""
    queue_depth: int = 0
    capabilities: list[str] = field(default_factory=list)
    version: str = ""
    auth_mode: str = ""
    nvenc: bool = False
    encoder: str = ""
    seen_at: float = field(default_factory=time.time)

    @property
    def url(self) -> str:
        host = self.ip_local or self.hostname
        return f"http://{host}:{self.port}" if host and self.port else ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "hostname": self.hostname,
            "ip_local": self.ip_local,
            "port": self.port,
            "url": self.url,
            "gpu_name": self.gpu_name,
            "vram_total_mb": self.vram_total_mb,
            "vram_free_mb": self.vram_free_mb,
            "status": self.status,
            "queue_depth": self.queue_depth,
            "capabilities": list(self.capabilities),
            "version": self.version,
            "auth_mode": self.auth_mode,
            "nvenc": self.nvenc,
            "encoder": self.encoder,
            "seen_at": self.seen_at,
        }


def _parse(payload: dict[str, Any]) -> DiscoveredWorker | None:
    worker_id = str(payload.get("worker_id") or "").strip()
    if not worker_id:
        return None
    try:
        port = int(payload.get("port") or 0)
    except (TypeError, ValueError):
        port = 0
    return DiscoveredWorker(
        worker_id=worker_id,
        hostname=str(payload.get("hostname") or ""),
        ip_local=str(payload.get("ip_local") or payload.get("ip") or ""),
        port=port,
        gpu_name=str(payload.get("gpu_name") or ""),
        vram_total_mb=int(payload.get("vram_total_mb") or 0),
        vram_free_mb=int(payload.get("vram_free_mb") or 0),
        status=str(payload.get("status") or ""),
        queue_depth=int(payload.get("queue_depth") or 0),
        capabilities=[str(item) for item in payload.get("capabilities") or []],
        version=str(payload.get("version") or ""),
        auth_mode=str(payload.get("auth_mode") or ""),
        nvenc=bool(payload.get("nvenc")),
        encoder=str(payload.get("encoder") or ""),
    )


class GpuDiscovery:
    """Listen for UDP beacons and keep a TTL-scoped peer table."""

    def __init__(
        self,
        *,
        port: int = DEFAULT_DISCOVERY_PORT,
        ttl_sec: float = DEFAULT_PEER_TTL_SEC,
    ) -> None:
        self.port = int(port)
        self.ttl_sec = max(float(ttl_sec), 1.0)
        self._peers: dict[str, DiscoveredWorker] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def peers(self) -> list[dict[str, Any]]:
        cutoff = time.time() - self.ttl_sec
        with self._lock:
            stale = [key for key, peer in self._peers.items() if peer.seen_at < cutoff]
            for key in stale:
                self._peers.pop(key, None)
            peers = list(self._peers.values())
        return [peer.as_dict() for peer in sorted(peers, key=lambda item: item.worker_id)]

    def ingest(self, payload: dict[str, Any]) -> bool:
        """Merge one beacon payload; exposed for tests and manual injection."""

        peer = _parse(payload)
        if peer is None:
            return False
        with self._lock:
            self._peers[peer.worker_id] = peer
        return True

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="vf-gpu-discovery",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def _loop(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", self.port))
            sock.settimeout(0.5)
        except OSError:
            return
        try:
            while not self._stop.is_set():
                try:
                    data, _address = sock.recvfrom(65535)
                except TimeoutError:
                    continue
                except OSError:
                    break
                try:
                    payload = json.loads(data.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    continue
                if isinstance(payload, dict):
                    self.ingest(payload)
        finally:
            sock.close()


def _merge_workers(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for item in group:
            key = str(item.get("worker_id") or item.get("url") or "")
            if not key:
                continue
            current = merged.get(key)
            if current is None or len(item) > len(current):
                merged[key] = item
    return sorted(
        merged.values(),
        key=lambda item: (
            str(item.get("worker_id") or ""),
            str(item.get("url") or ""),
        ),
    )


def mdns_workers(*, timeout_sec: float = 1.0) -> list[dict[str, Any]]:
    """Discover workers advertising ``_videoflow._tcp.local.`` when zeroconf exists.

    mDNS is optional: the worker still advertises over UDP and the client still
    scans the local subnets when zeroconf is not installed.
    """

    try:
        import zeroconf
    except Exception:  # noqa: BLE001 - optional dependency
        return []
    found: dict[str, dict[str, Any]] = {}
    event = threading.Event()

    class Listener:
        def add_service(self, zc: Any, service_type: str, name: str) -> None:
            info = zc.get_service_info(service_type, name, timeout=1000)
            if info is None:
                return
            properties = {
                key.decode("utf-8", "replace"): value.decode("utf-8", "replace")
                for key, value in (info.properties or {}).items()
                if isinstance(key, bytes)
            }
            addresses = [
                socket.inet_ntoa(address)
                for address in info.addresses
                if len(address) == socket.inet_aton("0.0.0.0").__len__()
            ]
            ipv4 = next(
                (
                    address
                    for address in addresses
                    if not address.startswith("127.")
                ),
                addresses[0] if addresses else "",
            )
            worker_id = str(properties.get("worker_id") or name.split(".")[0])
            found[worker_id] = {
                "worker_id": worker_id,
                "hostname": str(properties.get("hostname") or info.server or ""),
                "ip_local": ipv4,
                "port": int(info.port or 0),
                "url": f"http://{ipv4}:{info.port}" if ipv4 and info.port else "",
                "gpu_name": str(properties.get("gpu_name") or ""),
                "vram_total_mb": int(properties.get("vram_total_mb") or 0),
                "vram_free_mb": int(properties.get("vram_free_mb") or 0),
                "status": str(properties.get("status") or ""),
                "queue_depth": int(properties.get("queue_depth") or 0),
                "capabilities": [
                    item
                    for item in str(properties.get("capabilities") or "").split(",")
                    if item
                ],
                "version": str(properties.get("version") or ""),
                "auth_mode": str(properties.get("auth_mode") or ""),
                "nvenc": str(properties.get("nvenc") or "").lower()
                in {"1", "true", "yes"},
                "encoder": str(properties.get("encoder") or ""),
                "seen_at": time.time(),
                "transport": "mdns",
            }

        def update_service(self, zc: Any, service_type: str, name: str) -> None:
            self.add_service(zc, service_type, name)

        def remove_service(self, zc: Any, service_type: str, name: str) -> None:
            return None

    try:
        zc = zeroconf.Zeroconf()
        browsers = [
            zeroconf.ServiceBrowser(
                zc, service_type, Listener()
            )
            for service_type in (
                "_videoflow._tcp.local.",
                "_videoflow-gpu._tcp.local.",
            )
        ]
        try:
            event.wait(max(0.2, float(timeout_sec)))
        finally:
            for browser in browsers:
                browser.cancel()
            zc.close()
    except Exception:  # noqa: BLE001 - mDNS is best-effort
        return []
    return sorted(found.values(), key=lambda item: item["worker_id"])


def discover_workers(
    *,
    timeout_sec: float = 1.5,
    port: int = DEFAULT_DISCOVERY_PORT,
    include_mdns: bool = True,
) -> list[dict[str, Any]]:
    """Listen for UDP beacons, add optional mDNS peers, and deduplicate."""

    discovery = GpuDiscovery(port=port)
    discovery.start()
    try:
        time.sleep(max(0.1, float(timeout_sec)))
        peers = discovery.peers()
    finally:
        discovery.stop()
    mdns = mdns_workers(timeout_sec=min(max(0.2, float(timeout_sec)), 2.0)) if include_mdns else []
    return _merge_workers(peers, mdns)


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

    from concurrent.futures import ThreadPoolExecutor

    found: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(int(max_workers), 64))) as pool:
        for item in pool.map(lambda address: _probe_worker(address, port, timeout), addresses):
            if item is not None:
                found.append(item)
    merged = _merge_workers(found)
    with _SCAN_LOCK:
        _SCAN_CACHE[key] = (now, merged)
    return [dict(item) for item in merged]


__all__ = [
    "DEFAULT_DISCOVERY_PORT",
    "DiscoveredWorker",
    "GpuDiscovery",
    "discover_workers",
    "local_ipv4_addresses",
    "local_subnets",
    "mdns_workers",
    "scan_workers",
]
