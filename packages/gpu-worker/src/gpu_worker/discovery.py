"""UDP broadcast beacon for zero-configuration worker discovery."""

from __future__ import annotations

import contextlib
import json
import socket
import threading
from typing import Any

from gpu_worker import __version__
from gpu_worker.gpu import detect_gpu


def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            return str(probe.getsockname()[0])
    except OSError:
        return "127.0.0.1"


class DiscoveryBeacon:
    """Advertise a worker on the LAN every two seconds."""

    def __init__(
        self,
        *,
        worker_id: str,
        port: int,
        advertise_port: int,
        health: Any = None,
        interval: float = 2.0,
    ) -> None:
        self.worker_id = worker_id
        self.port = int(port)
        self.advertise_port = int(advertise_port)
        self.health = health
        self.interval = max(float(interval), 0.5)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._zeroconf: Any = None
        self._service_info: Any = None

    def payload(self) -> dict[str, Any]:
        gpu = detect_gpu()
        status = "idle"
        capabilities: list[str] = []
        queue_depth = 0
        auth_mode = "token"
        nvenc = False
        encoder = "libx264"
        if callable(self.health):
            try:
                health = self.health() or {}
            except Exception:  # noqa: BLE001 - beacon must not crash the worker
                health = {}
            status = str(health.get("status") or status)
            capabilities = [str(item) for item in health.get("capabilities") or []]
            queue_depth = int(health.get("queue_depth") or 0)
            auth_mode = str(health.get("auth_mode") or auth_mode)
            nvenc = bool(health.get("nvenc"))
            encoder = str(health.get("encoder") or encoder)
        return {
            "worker_id": self.worker_id,
            "hostname": socket.gethostname(),
            "ip_local": _local_ip(),
            "port": self.port,
            "gpu_name": gpu.name,
            "vram_total_mb": gpu.vram_total_mb,
            "vram_free_mb": gpu.vram_free_mb,
            "status": status,
            "queue_depth": queue_depth,
            "capabilities": capabilities,
            "auth_mode": auth_mode,
            "nvenc": nvenc,
            "encoder": encoder,
            "version": __version__,
        }

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._start_mdns()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="gpu-worker-discovery",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self._stop_mdns()

    def _start_mdns(self) -> None:
        """Advertise through mDNS when zeroconf is installed (optional)."""

        try:
            from zeroconf import ServiceInfo, Zeroconf
        except Exception:  # noqa: BLE001 - optional dependency
            return
        try:
            payload = self.payload()
            address = socket.inet_aton(str(payload["ip_local"]))
            properties = {
                "worker_id": self.worker_id,
                "hostname": str(payload["hostname"]),
                "gpu_name": str(payload["gpu_name"]),
                "vram_total_mb": str(payload["vram_total_mb"]),
                "vram_free_mb": str(payload["vram_free_mb"]),
                "status": str(payload["status"]),
                "queue_depth": str(payload["queue_depth"]),
                "capabilities": ",".join(str(item) for item in payload["capabilities"]),
                "version": str(payload["version"]),
                "auth_mode": str(payload["auth_mode"]),
                "nvenc": "1" if payload["nvenc"] else "0",
                "encoder": str(payload["encoder"]),
            }
            info = ServiceInfo(
                "_videoflow._tcp.local.",
                f"{self.worker_id}._videoflow._tcp.local.",
                addresses=[address],
                port=self.port,
                properties=properties,
                server=f"{socket.gethostname()}.local.",
            )
            zc = Zeroconf()
            zc.register_service(info)
            self._zeroconf = zc
            self._service_info = info
        except Exception:  # noqa: BLE001 - mDNS is best-effort
            self._stop_mdns()

    def _stop_mdns(self) -> None:
        zc = self._zeroconf
        info = self._service_info
        self._zeroconf = None
        self._service_info = None
        if zc is None:
            return
        with contextlib.suppress(Exception):
            if info is not None:
                zc.unregister_service(info)
        with contextlib.suppress(Exception):
            zc.close()

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            self._send()

    def _send(self) -> None:
        data = json.dumps(self.payload(), separators=(",", ":")).encode("utf-8")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.sendto(data, ("255.255.255.255", self.advertise_port))
        except OSError:
            return


__all__ = ["DiscoveryBeacon"]
