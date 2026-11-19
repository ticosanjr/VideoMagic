from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace

PACKAGE_SRC = Path(__file__).resolve().parents[2] / "packages" / "gpu-worker" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from gpu_worker import discovery as worker_discovery  # noqa: E402
from vf_compute.discovery import GpuDiscovery  # noqa: E402

PAYLOAD = {
    "worker_id": "worker-1",
    "hostname": "gpu-host",
    "ip_local": "192.168.1.20",
    "port": 8766,
    "gpu_name": "RTX 3060",
    "vram_total_mb": 12288,
    "vram_free_mb": 8192,
    "status": "idle",
    "queue_depth": 0,
    "capabilities": ["asr", "render_nvenc"],
    "version": "3.4.0",
}


def test_discovery_ingests_peers_and_expires_them() -> None:
    discovery = GpuDiscovery(ttl_sec=5)
    assert discovery.ingest(PAYLOAD) is True
    peers = discovery.peers()
    assert peers[0]["worker_id"] == "worker-1"
    assert peers[0]["url"] == "http://192.168.1.20:8766"
    assert discovery.ingest({"hostname": "missing-id"}) is False

    peer = discovery._peers["worker-1"]
    peer.seen_at = time.time() - 10
    assert discovery.peers() == []


def test_worker_beacon_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        worker_discovery,
        "detect_gpu",
        lambda: SimpleNamespace(
            name="RTX 3060",
            vram_total_mb=12288,
            vram_free_mb=7000,
        ),
    )
    monkeypatch.setattr(worker_discovery, "_local_ip", lambda: "192.168.1.20")
    beacon = worker_discovery.DiscoveryBeacon(
        worker_id="worker-1",
        port=8766,
        advertise_port=8767,
        health=lambda: {
            "status": "idle",
            "capabilities": ["asr"],
            "queue_depth": 1,
        },
    )
    payload = beacon.payload()
    assert payload["worker_id"] == "worker-1"
    assert payload["ip_local"] == "192.168.1.20"
    assert payload["capabilities"] == ["asr"]
    assert payload["queue_depth"] == 1


def test_worker_beacon_sends_udp(monkeypatch) -> None:
    sent: list[tuple[bytes, tuple[str, int]]] = []

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def setsockopt(self, *args):
            return None

        def sendto(self, data, address):
            sent.append((data, address))

    monkeypatch.setattr(worker_discovery.socket, "socket", lambda *args: FakeSocket())
    monkeypatch.setattr(worker_discovery, "_local_ip", lambda: "127.0.0.1")
    beacon = worker_discovery.DiscoveryBeacon(
        worker_id="worker-1",
        port=8766,
        advertise_port=8767,
        health=lambda: {"status": "idle"},
    )
    beacon._send()
    assert sent and sent[0][1] == ("255.255.255.255", 8767)
    assert b"worker-1" in sent[0][0]
