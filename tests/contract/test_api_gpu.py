from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from vf_shared.compute.models import JobStatus, WorkerHealth

from videoflow.api import routes_gpu
from videoflow.application.settings import load_settings


class FakeClient:
    def submit(self, capability: str, params=None, inputs=None, **kwargs) -> str:
        assert capability == "selftest"
        return "selftest-job"

    def wait(self, job_id: str, timeout: float = 30.0) -> JobStatus:
        return JobStatus(job_id=job_id, state="succeeded")

    def unload_models(self, name: str = "") -> dict[str, object]:
        return {"unloaded": [name or "all"], "loaded_models": []}

    def validate_shared(self, path: str) -> dict[str, object]:
        return {"ok": True, "path": path}


class FakeRouter:
    mode = "auto"
    worker_url = "http://192.168.1.45:8766"
    execution_node = "remote_gpu:worker-1"
    fallback_local = True

    def __init__(self) -> None:
        self.client = FakeClient()

    def health(self, force: bool = False) -> WorkerHealth:
        return WorkerHealth(
            available=True,
            worker_id="worker-1",
            gpu_name="RTX 3060",
            vram_free_mb=4096,
            vram_total_mb=12288,
            capabilities=["asr"],
            auth_mode="lan_open",
            nvenc=True,
            encoder="nvenc",
        )


def _app() -> FastAPI:
    app = FastAPI()
    routes_gpu.register_gpu_routes(app)
    return app


def test_gpu_selftest_route_runs_a_worker_job(monkeypatch) -> None:
    monkeypatch.setattr(routes_gpu, "router_from_settings", lambda settings: FakeRouter())
    client = TestClient(_app())
    response = client.post("/api/v1/gpu/selftest")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["job_id"] == "selftest-job"
    assert payload["state"] == "succeeded"


def test_gpu_settings_patch_and_status(monkeypatch) -> None:
    monkeypatch.setattr(routes_gpu, "router_from_settings", lambda settings: FakeRouter())
    monkeypatch.setattr(
        routes_gpu,
        "compute_status",
        lambda **kwargs: {
            "ok": True,
            "mode": "auto",
            "execution_node": "remote_gpu:worker-1",
            "available": True,
        },
    )
    client = TestClient(_app())
    status = client.get("/api/v1/gpu/status")
    assert status.status_code == 200
    assert status.json()["status"]["execution_node"] == "remote_gpu:worker-1"

    patched = client.patch(
        "/api/v1/gpu/settings",
        json={
            "mode": "local_only",
            "capabilities": {"asr": False},
            "max_vram_mb": 6144,
            "fallback_local": False,
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["gpu"]["mode"] == "local_only"
    assert patched.json()["gpu"]["capabilities"]["asr"] is False
    assert patched.json()["gpu"]["max_vram_mb"] == 6144
    saved = load_settings()
    assert saved.gpu.mode == "local_only"
    assert saved.gpu.fallback_local is False


def test_gpu_connect_requires_url_and_token(monkeypatch) -> None:
    monkeypatch.setattr(routes_gpu, "router_from_settings", lambda settings: FakeRouter())
    client = TestClient(_app())
    invalid = client.post("/api/v1/gpu/connect", json={"worker_url": "ftp://bad"})
    assert invalid.status_code == 400
    missing_token = client.post(
        "/api/v1/gpu/connect",
        json={"worker_url": "http://192.168.1.45:8766"},
    )
    assert missing_token.status_code == 400
    assert missing_token.json()["detail"]["code"] == "token_required"

    connected = client.post(
        "/api/v1/gpu/connect",
        json={
            "worker_url": "http://192.168.1.45:8766",
            "token": "secret",
            "worker_id": "worker-1",
        },
    )
    assert connected.status_code == 200, connected.text
    assert connected.json()["connected"] is True
    assert load_settings().gpu.worker_url == "http://192.168.1.45:8766"


def test_gpu_discovery_and_resource_routes(monkeypatch) -> None:
    monkeypatch.setattr(routes_gpu, "router_from_settings", lambda settings: FakeRouter())
    client = TestClient(_app())
    disabled = client.patch("/api/v1/gpu/settings", json={"discovery_enabled": False})
    assert disabled.status_code == 200
    assert client.get("/api/v1/gpu/discovery").json() == {
        "ok": True,
        "enabled": False,
        "workers": [],
    }

    unload = client.post("/api/v1/gpu/unload", json={"name": "asr"})
    assert unload.status_code == 200
    assert unload.json()["result"]["unloaded"] == ["asr"]
    shared = client.post("/api/v1/gpu/shared/validate", json={"path": "renders/out.mp4"})
    assert shared.status_code == 200
    assert shared.json()["result"]["path"] == "renders/out.mp4"
    benchmark = client.post("/api/v1/gpu/benchmark")
    assert benchmark.status_code == 200
    assert benchmark.json()["kind"] == "connectivity"


def test_gpu_unload_requires_a_worker(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    client = TestClient(_app())
    response = client.post("/api/v1/gpu/unload", json={})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "gpu_not_connected"


def test_gpu_discovery_and_worker_list(monkeypatch) -> None:
    import vf_shared.compute.discovery as discovery

    monkeypatch.setattr(
        discovery,
        "discover_workers",
        lambda timeout_sec=1.5, **_: [{"worker_id": "worker-1", "url": "http://gpu:8766"}],
    )
    monkeypatch.setattr(routes_gpu, "router_from_settings", lambda settings: FakeRouter())
    client = TestClient(_app())
    found = client.get("/api/v1/gpu/discovery?timeout_sec=0.4")
    assert found.status_code == 200
    assert found.json()["workers"][0]["worker_id"] == "worker-1"

    connected = client.post(
        "/api/v1/gpu/connect",
        json={
            "worker_url": "http://192.168.1.45:8766",
            "token": "secret",
        },
    )
    assert connected.status_code == 200
    workers = client.get("/api/v1/gpu/workers")
    assert workers.status_code == 200
    assert workers.json()["workers"]

    disconnected = client.post("/api/v1/gpu/disconnect")
    assert disconnected.status_code == 200
    assert load_settings().gpu.worker_url == ""


def test_gpu_shared_validate_requires_a_path(monkeypatch) -> None:
    monkeypatch.setattr(routes_gpu, "router_from_settings", lambda settings: FakeRouter())
    client = TestClient(_app())
    connected = client.post(
        "/api/v1/gpu/connect",
        json={
            "worker_url": "http://192.168.1.45:8766",
            "token": "secret",
        },
    )
    assert connected.status_code == 200
    missing = client.post("/api/v1/gpu/shared/validate", json={"path": ""})
    assert missing.status_code == 200
    assert missing.json()["result"]["path"] == "videoflow-probe.txt"


def test_gpu_connect_accepts_lan_open_worker_without_token(monkeypatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(routes_gpu, "router_from_settings", lambda settings: FakeRouter())

    class LanOpenClient:
        def __init__(self, url, token):
            self.url = url
            self.token = token

        def health(self, timeout=None):
            return SimpleNamespace(
                available=True,
                auth_mode="lan_open",
                nvenc=False,
                encoder="libx264",
            )

    monkeypatch.setattr("vf_shared.compute.client.GPUWorkerClient", LanOpenClient)
    client = TestClient(_app())
    response = client.post(
        "/api/v1/gpu/connect",
        json={"worker_url": "http://192.168.1.45:8766"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"]["auth_mode"] == "lan_open"
