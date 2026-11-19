"""Compute placement status exposed to MCP capabilities and job telemetry."""

from __future__ import annotations

from typing import Any

from vf_compute import ComputeRouter


def compute_status(router: ComputeRouter | None = None) -> dict[str, Any]:
    """Return local/remote placement details without failing the caller."""

    try:
        resolved = router or ComputeRouter.from_env()
    except Exception as exc:  # noqa: BLE001 - status must never break capabilities
        return {
            "ok": False,
            "mode": "local",
            "execution_node": "local",
            "available": False,
            "message": f"compute router unavailable: {exc}",
        }
    try:
        health = resolved.health()
    except Exception as exc:  # noqa: BLE001 - health is advisory here
        return {
            "ok": False,
            "mode": resolved.mode,
            "worker_url": resolved.worker_url,
            "execution_node": "local",
            "available": False,
            "message": f"worker health failed: {exc}",
        }
    return {
        "ok": True,
        "mode": resolved.mode,
        "worker_url": resolved.worker_url,
        "execution_node": resolved.execution_node,
        "available": health.available,
        "worker_id": health.worker_id,
        "hostname": health.hostname,
        "ip_local": health.ip_local,
        "port": health.port,
        "gpu_name": health.gpu_name,
        "vram_free_mb": health.vram_free_mb,
        "vram_total_mb": health.vram_total_mb,
        "vram_used_mb": health.vram_used_mb,
        "gpu_utilization": health.gpu_utilization,
        "temperature_c": health.temperature_c,
        "capabilities": list(health.capabilities),
        "models": list(health.models_loaded),
        "queue_depth": health.queue_depth,
        "message": health.message,
    }


def execute_capability(
    capability: str,
    remote_fn: Any,
    local_fn: Any,
    *,
    required_vram_mb: int = 0,
) -> dict[str, Any]:
    """Route one capability with a guaranteed local fallback."""

    router = ComputeRouter.from_env()
    return router.execute(
        capability,
        remote_fn,
        local_fn,
        required_vram_mb=required_vram_mb,
    )


__all__ = ["compute_status", "execute_capability"]
