from __future__ import annotations

import pytest
from vf_shared.compute.config import GpuConfig
from vf_shared.compute.errors import WorkerOfflineError
from vf_shared.compute.models import WorkerDecision, WorkerHealth
from vf_shared.compute.router import ComputeRouter

from videoflow.application.compute import guard_remote_policy
from videoflow.domain.errors import GpuWorkerOfflineError, VideoFlowError


class FakeClient:
    def __init__(self, url: str, token: str = "") -> None:
        self.url = url
        self.token = token

    def health(self, timeout: float | None = None) -> WorkerHealth:
        return WorkerHealth(
            available=True,
            worker_id="worker-new",
            gpu_name="RTX 3060",
            vram_free_mb=10_000,
            vram_total_mb=12_000,
            capabilities=["asr", "render_nvenc"],
        )

    def close(self) -> None:
        return None


class OfflineRouter:
    mode = "auto"

    def decide(self, capability: str, required_vram_mb: int = 0) -> WorkerDecision:
        return WorkerDecision(mode="local", reason="worker offline", capability=capability)

    def health(self, force: bool = False) -> WorkerHealth:
        return WorkerHealth(available=False, message="worker offline")


def test_health_rereads_gpu_config_without_restart(monkeypatch) -> None:
    from vf_shared.compute import router_health

    current = {
        "config": GpuConfig(
            mode="auto",
            worker_url="http://old-worker:8766",
            token="old-token",
            worker_id="worker-old",
            source="/tmp/gpu.json",
        )
    }
    monkeypatch.setattr(
        router_health, "load_gpu_config_file", lambda: current["config"]
    )
    monkeypatch.setattr(
        "vf_shared.compute.router.GPUWorkerClient",
        FakeClient,
    )
    router = ComputeRouter(mode="auto", worker_url="http://old-worker:8766")
    assert router.health(force=True).available is True

    # The UI repoints the worker after the router already probed it.
    current["config"] = GpuConfig(
        mode="auto",
        worker_url="http://new-worker:8766",
        token="new-token",
        worker_id="worker-new",
        source="/tmp/gpu.json",
    )

    health = router.health(force=True)

    assert router.worker_url == "http://new-worker:8766"
    assert router.token == "new-token"
    assert router.worker_source == "settings"
    assert health.available is True
    assert router.execution_node == "remote_gpu:worker-new"


def test_env_is_the_last_worker_source(monkeypatch) -> None:
    from vf_shared.compute import router_health

    monkeypatch.setattr(
        router_health, "load_gpu_config_file", lambda: GpuConfig()
    )
    monkeypatch.setattr(
        router_health,
        "env_worker_url",
        lambda: "http://env-worker:8766",
    )
    monkeypatch.setattr(
        router_health,
        "load_gpu_config",
        lambda: GpuConfig(
            mode="auto", worker_url="http://env-worker:8766", source="env"
        ),
    )
    monkeypatch.setattr(
        "vf_shared.compute.router.GPUWorkerClient",
        FakeClient,
    )
    monkeypatch.setattr(
        ComputeRouter, "discover", lambda self, timeout_sec=1.5: []
    )
    router = ComputeRouter(mode="auto", worker_url="", discovery_enabled=True)
    health = router.health(force=True)
    assert health.available is True
    assert router.worker_url == "http://env-worker:8766"
    assert router.worker_source == "env"


def test_from_env_marks_the_env_source(monkeypatch) -> None:
    from vf_shared.compute import router as router_module

    monkeypatch.setattr(
        router_module,
        "load_gpu_config",
        lambda: GpuConfig(
            mode="auto",
            worker_url="http://env-worker:8766",
            source="env",
        ),
    )
    router = ComputeRouter.from_env()
    assert router.worker_source == "env"


def test_remote_policy_raises_gpu_worker_offline() -> None:
    with pytest.raises(GpuWorkerOfflineError) as info:
        guard_remote_policy(
            OfflineRouter(),  # type: ignore[arg-type]
            "asr",
            compute_policy="remote",
        )
    assert info.value.code == "gpu_worker_offline"
    assert "gpu_required_for_operation" in str(info.value)


def test_auto_mode_uses_the_stable_degraded_reason() -> None:
    router = ComputeRouter(
        mode="auto",
        worker_url="http://worker:8766",
        client=type(
            "OfflineClient",
            (),
            {
                "health": lambda self, timeout=None: WorkerHealth(
                    available=False, message="offline"
                ),
                "close": lambda self: None,
            },
        )(),
    )
    result = router.execute("asr", lambda: "remote", lambda: "local")
    assert result["value"] == "local"
    assert result["degraded"] is True
    assert result["degraded_reason"] == "windows_gpu_offline_fallback_cpu"
    assert result["worker_source"] == "settings"


class _OfflineClient:
    def health(self, timeout: float | None = None) -> WorkerHealth:
        return WorkerHealth(available=False, message="offline")

    def close(self) -> None:
        return None


class _HealthyClient:
    def health(self, timeout: float | None = None) -> WorkerHealth:
        return WorkerHealth(
            available=True,
            worker_id="worker-1",
            gpu_name="RTX 3060",
            vram_free_mb=10_000,
            vram_total_mb=12_000,
            capabilities=["asr"],
        )

    def close(self) -> None:
        return None


def test_remote_policy_raises_before_running_locally() -> None:
    router = ComputeRouter(
        mode="auto", worker_url="http://worker:8766", client=_OfflineClient()
    )
    called: list[str] = []

    with pytest.raises(WorkerOfflineError) as info:
        router.execute(
            "asr",
            lambda: called.append("remote"),
            lambda: called.append("local"),
            compute_policy="remote",
        )

    assert info.value.code == "gpu_worker_offline"
    assert called == []


def test_typed_offline_error_is_forwarded_by_the_application_router() -> None:
    router = ComputeRouter(
        mode="auto",
        worker_url="http://worker:8766",
        client=_OfflineClient(),
        offline_error=GpuWorkerOfflineError,
    )

    with pytest.raises(GpuWorkerOfflineError) as info:
        router.execute("asr", lambda: None, lambda: None, compute_policy="remote")

    assert isinstance(info.value, VideoFlowError)
    assert isinstance(info.value, WorkerOfflineError)
    assert info.value.to_dict()["error_code"] == "gpu_worker_offline"


def test_remote_policy_does_not_fall_back_after_a_remote_failure() -> None:
    router = ComputeRouter(
        mode="auto", worker_url="http://worker:8766", client=_HealthyClient()
    )
    called: list[str] = []

    def remote() -> str:
        called.append("remote")
        raise RuntimeError("worker crashed")

    with pytest.raises(RuntimeError, match="worker crashed"):
        router.execute(
            "asr", remote, lambda: called.append("local"), compute_policy="remote"
        )

    assert called == ["remote"]


def test_auto_policy_keeps_the_stable_fallback_reason() -> None:
    router = ComputeRouter(
        mode="auto", worker_url="http://worker:8766", client=_OfflineClient()
    )

    outcome = router.execute("asr", lambda: "remote", lambda: "local")

    assert outcome["value"] == "local"
    assert outcome["degraded"] is True
    assert outcome["degraded_reason"] == "windows_gpu_offline_fallback_cpu"


def test_explicit_local_policy_is_not_reported_as_degraded() -> None:
    router = ComputeRouter(
        mode="auto", worker_url="http://worker:8766", client=_HealthyClient()
    )

    outcome = router.execute(
        "asr",
        lambda: (_ for _ in ()).throw(AssertionError("remote must not run")),
        lambda: "local",
        compute_policy="local",
    )

    assert outcome["value"] == "local"
    assert outcome["degraded"] is False
    assert outcome["degraded_reason"] == ""


def test_file_mode_change_applies_without_restart(monkeypatch) -> None:
    from vf_shared.compute import router_health

    monkeypatch.setattr(
        router_health,
        "load_gpu_config_file",
        lambda: GpuConfig(mode="local_only", source="/tmp/gpu.json"),
    )
    monkeypatch.setattr(
        router_health,
        "load_gpu_config",
        lambda: GpuConfig(mode="local_only", source="/tmp/gpu.json"),
    )
    router = ComputeRouter(mode="auto", worker_url="http://worker:8766")

    health = router.health(force=True)

    assert router.mode == "local_only"
    assert health.available is False
