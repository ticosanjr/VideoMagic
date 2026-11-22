from __future__ import annotations

from vf_shared.compute import router as router_module
from vf_shared.compute.models import WorkerHealth
from vf_shared.compute.router import ComputeRouter


class FakeClient:
    def __init__(self, url: str, token: str = "") -> None:
        self.url = url
        self.token = token

    def health(self, timeout: float | None = None) -> WorkerHealth:
        return WorkerHealth(
            available=True,
            worker_id="worker-1",
            gpu_name="RTX 3060",
            vram_free_mb=10_000,
            vram_total_mb=12_000,
            capabilities=["asr", "render_nvenc"],
            queue_depth=0,
        )

    def close(self) -> None:
        return None


def test_router_discovers_a_worker_when_no_url_is_configured(monkeypatch) -> None:
    monkeypatch.setattr(router_module, "GPUWorkerClient", FakeClient)
    monkeypatch.setattr(
        ComputeRouter,
        "discover",
        lambda self, timeout_sec=1.5: [
            {
                "worker_id": "worker-1",
                "url": "http://192.168.1.45:8766",
                "token": "",
            }
        ],
    )
    router = ComputeRouter(mode="auto", worker_url="", discovery_enabled=True)
    health = router.health(force=True)
    assert health.available is True
    assert router.worker_url == "http://192.168.1.45:8766"
    assert router.worker_source == "mdns"
    assert router.execution_node == "remote_gpu:worker-1"


def test_router_reports_no_worker_when_discovery_is_empty(monkeypatch) -> None:
    monkeypatch.setattr(ComputeRouter, "discover", lambda self, timeout_sec=1.5: [])
    router = ComputeRouter(mode="auto", worker_url="", discovery_enabled=True)
    health = router.health(force=True)
    assert health.available is False
    assert "not configured" in health.message


def test_router_uses_the_new_url_immediately(monkeypatch) -> None:
    monkeypatch.setattr(router_module, "GPUWorkerClient", FakeClient)
    router = ComputeRouter(mode="auto", worker_url="http://old:8766")
    router.set_worker("http://new:8766")
    router.health(force=True)
    assert router.worker_url == "http://new:8766"
