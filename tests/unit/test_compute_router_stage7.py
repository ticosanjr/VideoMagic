from __future__ import annotations

from pathlib import Path

from vf_shared.compute.models import JobStatus, WorkerHealth
from vf_shared.compute.router import ComputeRouter

from videoflow.application.capabilities import capability_manifest
from videoflow.application.compute import compute_status, execute_batch, execute_capability


class FakeClient:
    def __init__(self, *, free: int = 8192, shared_root: str = "") -> None:
        self.free = free
        self.shared_root = shared_root
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
                "shared_root": self.shared_root,
                "capabilities": ["asr", "render_nvenc", "segment_matte"],
            }
        )

    def upload_artifact(self, path: str | Path) -> str:
        return f"artifact:{Path(path).name}"

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
    router = ComputeRouter(client=client, min_vram_mb=0, offload_all_heavy=False)
    assert router.decide("asr").mode == "local"
    assert router.decide("render_nvenc").mode == "remote"
    assert router.decide("asr").execution_node == "local"


def test_router_respects_capability_settings() -> None:
    client = FakeClient(free=8192)
    router = ComputeRouter(
        client=client,
        min_vram_mb=0,
        allowed_capabilities={"asr"},
    )
    assert router.decide("asr").mode == "remote"
    disabled = router.decide("render_nvenc")
    assert disabled.mode == "local"
    assert "disabled" in disabled.reason


def test_router_execute_remote_and_local_fallback() -> None:
    client = FakeClient()
    router = ComputeRouter(client=client, min_vram_mb=0, offload_all_heavy=False)
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
    router = ComputeRouter(client=client, min_vram_mb=0, offload_all_heavy=False)
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


def test_router_uses_shared_inputs_without_uploading(tmp_path: Path) -> None:
    local_root = tmp_path / "shared"
    source = local_root / "media" / "voice.wav"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"audio")
    client = FakeClient(shared_root=r"Z:\videoflow")
    router = ComputeRouter(
        client=client,
        min_vram_mb=0,
        shared_local_root=str(local_root),
    )
    result = router.submit(
        "asr",
        {
            "inputs": [str(source)],
            "params": {"audio": str(source), "language": "pt"},
            "timeout_sec": 5,
        },
    )
    submitted = client.submitted[0]
    assert submitted["shared_inputs"] == ["media/voice.wav"]
    assert submitted["params"]["audio"] == "__VF_INPUT_0__"
    assert submitted["shared_root"] == r"Z:\videoflow"
    assert result["shared_inputs"] == ["media/voice.wav"]
    assert result["transfer"]["upload_bytes"] == 0


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
        "videoflow.application.compute.router_from_settings",
        lambda settings=None: broken(),
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
        "videoflow.application.compute.router_from_settings",
        lambda settings=None: Unhealthy(),
    )
    status = compute_status()
    assert status["ok"] is False
    assert "health failed" in status["message"]


def test_execute_capability_uses_router(monkeypatch) -> None:
    class Router:
        fallback_local = True

        def execute(
            self,
            capability,
            remote_fn,
            local_fn,
            *,
            required_vram_mb=0,
            fallback_local=True,
            compute_policy="auto",
            allow_slow_cpu_fallback=False,
        ):
            return {
                "value": local_fn(),
                "execution_node": "local",
                "fallback_reason": "test",
            }

    monkeypatch.setattr(
        "videoflow.application.compute.router_from_settings",
        lambda settings=None: Router(),
    )
    result = execute_capability("asr", lambda: "remote", lambda: "local")
    assert result["value"] == "local"
    assert result["fallback_reason"] == "test"


def test_execute_batch_keeps_going_after_worker_failure(monkeypatch) -> None:
    class Client:
        def __init__(self) -> None:
            self.health_calls = 0

        def health(self, timeout: float | None = None) -> WorkerHealth:
            self.health_calls += 1
            return WorkerHealth(
                available=self.health_calls == 1,
                worker_id="worker-1",
                vram_free_mb=8192,
                capabilities=["asr"],
            )

    client = Client()
    router = ComputeRouter(client=client, min_vram_mb=0, offload_all_heavy=False)
    monkeypatch.setattr(
        "videoflow.application.compute.router_from_settings",
        lambda settings=None: router,
    )

    def remote(index: int) -> str:
        if index >= 2:
            raise RuntimeError("worker dropped")
        return f"remote-{index}"

    results = execute_batch(
        "asr",
        list(range(5)),
        remote,
        lambda index: f"local-{index}",
    )
    assert [item["value"] for item in results] == [
        "remote-0",
        "remote-1",
        "local-2",
        "local-3",
        "local-4",
    ]
    assert sum(item["remote"] for item in results) == 2
    assert results[-1]["fallback_reason"]


def test_heavy_capability_forces_remote_even_when_vram_and_queue_are_tight() -> None:
    client = FakeClient(free=0)
    router = ComputeRouter(
        client=client,
        min_vram_mb=4096,
        max_queue=0,
        max_gpu_utilization=1.0,
        offload_all_heavy=True,
    )
    decision = router.decide("asr")
    assert decision.mode == "remote"
    assert decision.is_remote is True


def test_heavy_auto_policy_fails_closed_when_worker_is_offline() -> None:
    class Offline:
        def health(self, timeout: float | None = None) -> WorkerHealth:
            return WorkerHealth(available=False, message="offline")

        def close(self) -> None:
            return None

    router = ComputeRouter(client=Offline(), offload_all_heavy=True)
    try:
        router.execute("asr", lambda: "remote", lambda: "local")
    except Exception as exc:  # noqa: BLE001 - assert the typed code
        assert getattr(exc, "code", "") == "gpu_worker_offline"
    else:  # pragma: no cover - fail-closed must raise
        raise AssertionError("heavy auto policy must fail closed")
