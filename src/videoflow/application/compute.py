"""Compute placement status exposed to MCP capabilities and job telemetry."""

from __future__ import annotations

from typing import Any

from vf_shared.compute import ComputeRouter


def router_from_settings(settings: Any | None = None) -> ComputeRouter:
    """Build a router from persisted ``GpuSettings`` and the secret store."""

    if settings is None:
        from videoflow.application.settings import load_settings

        settings = load_settings()
    gpu = settings.gpu
    token = ""
    try:
        from videoflow.application.secrets import get_secret

        token = get_secret(gpu.worker_token_secret)
    except Exception:  # noqa: BLE001 - a missing secret means local fallback
        token = ""
    return ComputeRouter(
        mode=gpu.mode,
        worker_url=gpu.worker_url,
        token=token,
        transport=gpu.transport,
        shared_local_root=gpu.shared_linux_path,
        min_vram_mb=2048,
        max_queue=2,
        fallback_local=gpu.fallback_local,
        max_gpu_utilization=float(gpu.max_gpu_utilization_pct),
        allowed_capabilities={
            capability for capability, enabled in gpu.capabilities.items() if enabled
        },
        discovery_enabled=gpu.discovery_enabled,
    )


def guard_remote_policy(
    router: ComputeRouter,
    capability: str,
    *,
    compute_policy: str,
    allow_slow_cpu_fallback: bool = False,
    error_cls: type[Exception] = RuntimeError,
) -> None:
    """Fail fast when the caller explicitly requires the GPU."""

    if compute_policy != "remote" or allow_slow_cpu_fallback:
        return
    decision = router.decide(capability)
    if decision.is_remote:
        return
    raise error_cls(
        "gpu_required_for_operation: "
        f"{decision.reason}. Pass allow_slow_cpu_fallback=True to run on CPU."
    )


def compute_status(
    router: ComputeRouter | None = None,
    settings: Any | None = None,
) -> dict[str, Any]:
    """Return local/remote placement details without failing the caller."""

    try:
        resolved = router or router_from_settings(settings)
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
        "transport": getattr(resolved, "transport", "auto"),
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
        "auth_mode": getattr(health, "auth_mode", ""),
        "nvenc": getattr(health, "nvenc", False),
        "encoder": getattr(health, "encoder", ""),
        "version": getattr(health, "version", ""),
        "nvenc_error": getattr(health, "nvenc_error", ""),
        "disk_free_mb": getattr(health, "disk_free_mb", 0),
        "min_free_disk_mb": getattr(health, "min_free_disk_mb", 0),
        "uptime_sec": getattr(health, "uptime_sec", 0.0),
        "job_retention_hours": getattr(health, "job_retention_hours", 0.0),
        "lan_urls": list(getattr(health, "lan_urls", []) or []),
        "warmup": dict(getattr(health, "warmup", {}) or {}),
        "current_job": dict(getattr(health, "current_job", {}) or {}),
        "allowed_clients": list(getattr(health, "allowed_clients", []) or []),
        "token_only": bool(getattr(health, "token_only", False)),
        "fallback_local": resolved.fallback_local,
        "max_gpu_utilization_pct": getattr(resolved, "max_gpu_utilization", 0.0),
        "allowed_capabilities": (
            sorted(getattr(resolved, "allowed_capabilities", None))
            if getattr(resolved, "allowed_capabilities", None) is not None
            else []
        ),
    }


def execute_capability(
    capability: str,
    remote_fn: Any,
    local_fn: Any,
    *,
    required_vram_mb: int = 0,
    settings: Any | None = None,
) -> dict[str, Any]:
    """Route one capability with a guaranteed local fallback."""

    router = router_from_settings(settings)
    return router.execute(
        capability,
        remote_fn,
        local_fn,
        required_vram_mb=required_vram_mb,
        fallback_local=router.fallback_local,
    )


def execute_batch(
    capability: str,
    items: list[Any],
    remote_fn: Any,
    local_fn: Any,
    *,
    required_vram_mb: int = 0,
    settings: Any | None = None,
) -> list[dict[str, Any]]:
    """Route independent items, falling back locally after the circuit opens."""

    router = router_from_settings(settings)
    results: list[dict[str, Any]] = []
    for item in items:
        results.append(
            router.execute(
                capability,
                lambda item=item: remote_fn(item),
                lambda item=item: local_fn(item),
                required_vram_mb=required_vram_mb,
                fallback_local=router.fallback_local,
            )
        )
    return results


__all__ = [
    "compute_status",
    "execute_batch",
    "execute_capability",
    "guard_remote_policy",
    "router_from_settings",
]
