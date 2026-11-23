from __future__ import annotations

from vf_shared.compute.models import WorkerHealth
from vf_shared.compute.router import ComputeRouter


class FakeClient:
    def __init__(self, utilization: float) -> None:
        self.utilization = utilization

    def health(self, timeout: float | None = None) -> WorkerHealth:
        return WorkerHealth(
            available=True,
            worker_id="worker-1",
            gpu_name="RTX 3060",
            vram_free_mb=10_000,
            vram_total_mb=12_000,
            gpu_utilization=self.utilization,
            capabilities=["render_nvenc", "short_render"],
            queue_depth=0,
        )

    def close(self) -> None:
        return None


def _router(utilization: float, cap: float) -> ComputeRouter:
    return ComputeRouter(
        mode="auto",
        worker_url="http://worker:8766",
        max_gpu_utilization=cap,
        offload_all_heavy=False,
        client=FakeClient(utilization),  # type: ignore[arg-type]
    )


def test_remote_is_skipped_when_external_gpu_load_is_above_the_cap() -> None:
    decision = _router(utilization=81.0, cap=70.0).decide("render_nvenc")
    assert decision.mode == "local"
    assert "external GPU load" in decision.reason


def test_remote_is_allowed_at_or_below_the_cap() -> None:
    assert _router(utilization=70.0, cap=70.0).decide("render_nvenc").mode == "remote"
    assert _router(utilization=35.0, cap=70.0).decide("render_nvenc").mode == "remote"


def test_zero_disables_the_load_guard() -> None:
    assert _router(utilization=99.0, cap=0.0).decide("render_nvenc").mode == "remote"


def test_router_from_settings_passes_the_utilization_cap(monkeypatch) -> None:
    from videoflow.application.compute import router_from_settings
    from videoflow.application.settings import AppSettings, GpuSettings

    monkeypatch.setattr(
        "videoflow.application.secrets.get_secret", lambda name: ""
    )
    settings = AppSettings(gpu=GpuSettings(max_gpu_utilization_pct=55))
    router = router_from_settings(settings)
    assert router.max_gpu_utilization == 55.0
