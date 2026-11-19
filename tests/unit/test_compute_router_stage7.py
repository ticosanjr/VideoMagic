from __future__ import annotations

from pathlib import Path

from vf_compute.models import JobStatus, WorkerHealth
from vf_compute.router import ComputeRouter

from videoflow.application.capabilities import capability_manifest
from videoflow.application.compute import compute_status, execute_capability


class FakeClient:
    def __init__(self, *, free: int = 8192) -> None:
        self.free = free
        self.submitted: list[dict[str, object]] = []
        self.closed = False

    def health(self, timeout: float | None = None) -> WorkerHealth:
        return WorkerHealth.from_payload(
            {
                "available": True,
                "worker_id": "worker-1",
                "hostname": "gpu-host",
                "ip_local": "192.168.1.10",
                "port": 8766,
                "gpu_name": "RTX 3060",
                "vram_free_mb": self.free,
                "vram_total_mb": 12288,
                "capabilities": ["asr", "render_nvenc", "segment_matte"],
            }
        )

    def submit(self, capability: str, **kwargs: object) -> str:
        self.submitted.append({"capability": capability, **kwargs})
        return "job-1"

    def wait(self, job_id: str, timeout: float = 300.0, poll: float = 0.5) -> JobStatus:
        return JobStatus(
            job_id=job_id,
            state="succeeded",
            artifacts=["transcript.json"],
        )

    def download(self, job_id: str, name: str, target: str | Path) -> Path:
        path = Path(target)
        path.write_text('{"ok": true}', encoding="utf-8")
        return path

    def close(self) -> None:
        self.closed = True


def test_router_uses_capability_vram_costs() -> None:
    client = FakeClient(free=3000)
    router = ComputeRouter(client=client, min_vram_mb=0)
    assert router.decide("asr").mode == "local"
    assert router.decide("render_nvenc").mode == "remote"
    assert router.decide("asr").execution_node == "local"


def test_router_execute_remote_and_local_fallback() -> None:
    client = FakeClient()
    router = ComputeRouter(client=client, min_vram_mb=0)
    remote = router.execute("asr", lambda: "remote-value", lambda: "local-value")
    assert remote["value"] == "remote-value"
    assert remote["remote"] is True
    assert remote["execution_node"] == "remote_gpu:worker-1"
    assert remote["fallback_reason"] == ""

    def fail() -> str:
        raise RuntimeError("worker died")

    fallback = router.execute("asr", fail, lambda: "local-value")
    assert fallback["value"] == "local-value"
    assert fallback["remote"] is False
    assert "remote failed" in fallback["fallback_reason"]
    assert fallback["execution_node"] == "local"


def test_router_execute_skips_remote_when_capability_is_missing() -> None:
    client = FakeClient()
    router = ComputeRouter(client=client, min_vram_mb=0)
    result = router.execute("render_nvenc", lambda: "remote", lambda: "local")
    assert result["value"] == "remote"
    missing = router.execute("diarize", lambda: "remote", lambda: "local")
    assert missing["value"] == "local"
    assert "capability not available" in missing["fallback_reason"]


def test_router_submit_downloads_first_artifact(tmp_path: Path) -> None:
    client = FakeClient()
    router = ComputeRouter(client=client, min_vram_mb=0)
    result = router.submit(
        "asr",
        {"params": {"language": "pt"}, "timeout_sec": 5},
    )
    assert result["job_id"] == "job-1"
    assert Path(result["path"]).is_file()
    assert result["execution_node"] == "remote_gpu:worker-1"
    assert client.submitted[0]["capability"] == "asr"


def test_router_set_worker_and_disconnect() -> None:
    client = FakeClient()
    router = ComputeRouter(client=client, min_vram_mb=0)
    router.health()
    assert router.execution_node.startswith("remote_gpu:")
    router.disconnect()
    assert router.worker_url == ""
    assert router.execution_node == "local"
    assert client.closed is True


def test_compute_status_and_manifest_expose_local_fallback(monkeypatch) -> None:
    monkeypatch.delenv("VF_GPU_WORKER_URL", raising=False)
    monkeypatch.delenv("VF_GPU_WORKER_TOKEN", raising=False)
    status = compute_status()
    assert status["ok"] is True
    assert status["execution_node"] == "local"
    assert status["available"] is False
    entries = {entry["id"]: entry for entry in capability_manifest()}
    entry = entries["compute_router"]
    assert entry["status"] == "available"
    assert entry["execution_node"] == "local"
    assert entry["remote_available"] is False
    assert "compute" in entry


def test_compute_status_handles_router_failures(monkeypatch) -> None:
    def broken():
        raise RuntimeError("no router")

    monkeypatch.setattr(
        "videoflow.application.compute.ComputeRouter.from_env",
        classmethod(lambda cls: broken()),
    )
    status = compute_status()
    assert status["ok"] is False
    assert status["execution_node"] == "local"

    class Unhealthy:
        mode = "auto"
        worker_url = "http://worker"
        execution_node = "local"

        def health(self):
            raise RuntimeError("down")

    monkeypatch.setattr(
        "videoflow.application.compute.ComputeRouter.from_env",
        classmethod(lambda cls: Unhealthy()),
    )
    status = compute_status()
    assert status["ok"] is False
    assert "health failed" in status["message"]


def test_execute_capability_uses_router(monkeypatch) -> None:
    class Router:
        def execute(self, capability, remote_fn, local_fn, *, required_vram_mb=0):
            return {
                "value": local_fn(),
                "execution_node": "local",
                "fallback_reason": "test",
            }

    monkeypatch.setattr(
        "videoflow.application.compute.ComputeRouter.from_env",
        classmethod(lambda cls: Router()),
    )
    result = execute_capability("asr", lambda: "remote", lambda: "local")
    assert result["value"] == "local"
    assert result["fallback_reason"] == "test"
