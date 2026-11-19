"""LAN discovery of GPU workers through UDP broadcast beacons."""

from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any

DEFAULT_DISCOVERY_PORT = 8767
DEFAULT_PEER_TTL_SEC = 10.0


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


def discover_workers(
    *,
    timeout_sec: float = 1.5,
    port: int = DEFAULT_DISCOVERY_PORT,
) -> list[dict[str, Any]]:
    """Listen once for ``timeout_sec`` and return the peers seen."""

    discovery = GpuDiscovery(port=port)
    discovery.start()
    try:
        time.sleep(max(0.1, float(timeout_sec)))
        return discovery.peers()
    finally:
        discovery.stop()


__all__ = [
    "DEFAULT_DISCOVERY_PORT",
    "DiscoveredWorker",
    "GpuDiscovery",
    "discover_workers",
]
