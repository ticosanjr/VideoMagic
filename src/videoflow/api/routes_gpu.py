"""GPU status, pairing, discovery, benchmark, and resource routes."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from vf_shared.compute.config import clear_gpu_config, save_gpu_config

from videoflow.application.capabilities import clear_capability_cache
from videoflow.application.compute import compute_status, router_from_settings
from videoflow.application.secrets import get_secret, set_secret
from videoflow.application.settings import AppSettings, GpuSettings, load_settings, save_settings
from videoflow.application.win_worker_kit import build_worker_kit, kit_info
from videoflow.domain.errors import VideoFlowError


class GpuConnectRequest(BaseModel):
    worker_url: str = ""
    token: str = ""
    worker_id: str = ""
    mode: Literal["auto", "remote_preferred", "local_only", "local_gpu"] = "auto"
    transport: Literal["auto", "http", "shared"] = "auto"


class GpuSettingsPatch(BaseModel):
    mode: Literal["auto", "remote_preferred", "local_only", "local_gpu"] | None = None
    transport: Literal["auto", "http", "shared"] | None = None
    capabilities: dict[str, bool] | None = None
    shared_mount_enabled: bool | None = None
    shared_linux_path: str | None = None
    shared_windows_path: str | None = None
    max_vram_mb: int | None = Field(default=None, ge=4096, le=24576)
    max_gpu_utilization_pct: int | None = Field(default=None, ge=0, le=100)
    model_unload_ttl_sec: int | None = Field(default=None, ge=30, le=86400)
    fallback_local: bool | None = None
    discovery_enabled: bool | None = None


class GpuSharedRequest(BaseModel):
    path: str = ""


class GpuUnloadRequest(BaseModel):
    name: str = ""


def _current() -> AppSettings:
    return load_settings()


def _save_gpu(settings: AppSettings, gpu: GpuSettings) -> AppSettings:
    return save_settings(settings.model_copy(update={"gpu": gpu}))


def _validate_worker_url(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "code": "invalid_worker_url",
                "message": "worker_url must be an http(s) URL",
            },
        )
    return raw


def _require_router(settings: AppSettings):
    router = router_from_settings(settings)
    if not router.worker_url:
        raise HTTPException(
            status_code=409,
            detail={
                "ok": False,
                "code": "gpu_not_connected",
                "message": "Connect a GPU worker first.",
            },
        )
    return router


class WindowsKitRequest(BaseModel):
    token: str = ""
    worker_id: str = ""
    shared_windows_path: str = ""
    ffmpeg_path: str = ""
    include_worker_source: bool = True


def _register_worker_kit_routes(app: FastAPI) -> None:
    """Personal Windows worker kit download and metadata."""

    @app.post("/api/v1/gpu-worker/package")
    def package_gpu_worker(payload: WindowsKitRequest | None = None) -> FileResponse:
        request = payload or WindowsKitRequest()
        try:
            result = build_worker_kit(
                token=request.token,
                worker_id=request.worker_id,
                shared_windows_path=request.shared_windows_path,
                ffmpeg_path=Path(request.ffmpeg_path) if request.ffmpeg_path else None,
                include_worker_source=request.include_worker_source,
            )
        except (OSError, VideoFlowError) as exc:
            raise HTTPException(
                status_code=500,
                detail={"ok": False, "code": "win_kit_failed", "message": str(exc)},
            ) from exc
        return FileResponse(
            result.path,
            media_type="application/zip",
            filename=result.path.name,
        )

    @app.get("/api/v1/gpu-worker/package/info")
    def package_gpu_worker_info() -> dict[str, object]:
        info = kit_info()
        if info is None:
            return {
                "ok": False,
                "code": "win_kit_missing",
                "message": "No Windows worker kit has been generated yet.",
            }
        return info


def register_gpu_routes(app: FastAPI) -> None:
    """Register GPU acceleration status and control routes."""

    _register_worker_kit_routes(app)

    @app.get("/api/v1/gpu/status")
    def gpu_status() -> dict[str, Any]:
        settings = _current()
        status = compute_status(settings=settings)
        status["shared_mount_enabled"] = settings.gpu.shared_mount_enabled
        status["shared_linux_path"] = settings.gpu.shared_linux_path
        status["shared_windows_path"] = settings.gpu.shared_windows_path
        status["discovery_enabled"] = settings.gpu.discovery_enabled
        status["capabilities_enabled"] = dict(settings.gpu.capabilities)
        status["max_vram_mb"] = settings.gpu.max_vram_mb
        status["model_unload_ttl_sec"] = settings.gpu.model_unload_ttl_sec
        return {"ok": True, "status": status}

    @app.get("/api/v1/gpu/discovery")
    def gpu_discovery(timeout_sec: float = 1.5, scan: bool = True) -> dict[str, Any]:
        settings = _current()
        if not settings.gpu.discovery_enabled:
            return {"ok": True, "enabled": False, "workers": []}
        import time

        from vf_shared.compute.discovery import (
            discover_workers,
            local_subnets,
            mdns_workers,
            scan_workers,
        )

        started = time.perf_counter()
        timeout = max(0.2, min(float(timeout_sec), 5.0))
        udp = discover_workers(timeout_sec=timeout, include_mdns=False)
        mdns = mdns_workers(timeout_sec=min(timeout, 2.0))
        tcp: list[dict[str, Any]] = []
        if scan and not (udp or mdns):
            tcp = scan_workers(port=8766)
        merged: dict[str, dict[str, Any]] = {}
        for item in [*udp, *mdns, *tcp]:
            key = str(item.get("worker_id") or item.get("url"))
            current = merged.get(key)
            if current is None or len(item) > len(current):
                merged[key] = item
        workers = sorted(
            merged.values(), key=lambda item: str(item.get("worker_id") or "")
        )
        return {
            "ok": True,
            "enabled": True,
            "workers": workers,
            "diagnostics": {
                "udp": len(udp),
                "mdns": len(mdns),
                "tcp_scan": len(tcp),
                "scan_enabled": bool(scan),
                "subnets": local_subnets(),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                "udp_port": 8767,
                "tcp_port": 8766,
            },
        }

    @app.get("/api/v1/gpu/workers")
    def gpu_workers() -> dict[str, Any]:
        settings = _current()
        status = compute_status(settings=settings)
        workers = [status] if settings.gpu.worker_url else []
        return {"ok": True, "workers": workers}

    @app.post("/api/v1/gpu/connect")
    def gpu_connect(payload: GpuConnectRequest) -> dict[str, Any]:
        settings = _current()
        url = _validate_worker_url(payload.worker_url)
        token = payload.token.strip()
        stored = token or get_secret(settings.gpu.worker_token_secret)
        if token:
            set_secret(settings.gpu.worker_token_secret, token)
        elif not stored:
            from vf_shared.compute.client import GPUWorkerClient

            try:
                probe = GPUWorkerClient(url, "").health(timeout=3.0)
            except Exception as exc:  # noqa: BLE001 - report a typed connect error
                raise HTTPException(
                    status_code=400,
                    detail={
                        "ok": False,
                        "code": "token_required",
                        "message": (
                            "No token was supplied and the worker did not confirm "
                            f"LAN-open mode: {exc}"
                        ),
                    },
                ) from exc
            if not probe.available or probe.auth_mode != "lan_open":
                raise HTTPException(
                    status_code=400,
                    detail={
                        "ok": False,
                        "code": "token_required",
                        "message": (
                            "The worker requires a token. Enable LAN-open mode in "
                            "the Windows kit or paste the token under Advanced."
                        ),
                    },
                )
        gpu = settings.gpu.model_copy(
            update={
                "worker_url": url,
                "worker_id": payload.worker_id.strip(),
                "mode": payload.mode,
                "transport": payload.transport,
            }
        )
        updated = _save_gpu(settings, gpu)
        save_gpu_config(
            mode=gpu.mode,
            worker_url=url,
            token=stored or "",
            worker_id=gpu.worker_id,
            transport=gpu.transport,
        )
        clear_capability_cache()
        router = router_from_settings(updated)
        health = router.health(force=True)
        return {
            "ok": True,
            "connected": health.available,
            "status": compute_status(router=router, settings=updated),
        }

    @app.post("/api/v1/gpu/selftest")
    def gpu_selftest() -> dict[str, Any]:
        settings = _current()
        router = _require_router(settings)
        started = time.perf_counter()
        try:
            job_id = router.client.submit("selftest", params={}, inputs=[])
            status = router.client.wait(job_id, timeout=30.0)
        except Exception as exc:  # noqa: BLE001 - diagnostic endpoint
            raise HTTPException(
                status_code=502,
                detail={"ok": False, "code": "selftest_failed", "message": str(exc)},
            ) from exc
        if not status.ok:
            raise HTTPException(
                status_code=502,
                detail={
                    "ok": False,
                    "code": "selftest_failed",
                    "message": status.error or status.message or status.state,
                    "job_id": job_id,
                },
            )
        return {
            "ok": True,
            "job_id": job_id,
            "state": status.state,
            "elapsed_sec": round(time.perf_counter() - started, 3),
        }

    @app.get("/api/v1/gpu/activity")
    def gpu_activity() -> dict[str, Any]:
        settings = _current()
        try:
            router = _require_router(settings)
            return {"ok": True, "overview": router.client.overview(timeout=3.0)}
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 - activity is advisory
            return {"ok": False, "error": str(exc), "overview": {}}

    @app.post("/api/v1/gpu/disconnect")
    def gpu_disconnect() -> dict[str, Any]:
        settings = _current()
        updated = _save_gpu(
            settings,
            settings.gpu.model_copy(
                update={
                    "worker_url": "",
                    "worker_id": "",
                    "mode": "auto",
                    "transport": "auto",
                }
            ),
        )
        clear_gpu_config()
        clear_capability_cache()
        return {
            "ok": True,
            "status": compute_status(settings=updated),
        }

    @app.patch("/api/v1/gpu/settings")
    def gpu_settings(payload: GpuSettingsPatch) -> dict[str, Any]:
        settings = _current()
        updates = {
            key: value
            for key, value in payload.model_dump(exclude_none=True).items()
        }
        if "capabilities" in updates:
            merged = dict(settings.gpu.capabilities)
            merged.update(
                {
                    str(key): bool(value)
                    for key, value in updates["capabilities"].items()
                }
            )
            updates["capabilities"] = merged
        updated = _save_gpu(
            settings,
            settings.gpu.model_copy(update=updates),
        )
        if updated.gpu.worker_url:
            save_gpu_config(
                mode=updated.gpu.mode,
                worker_url=updated.gpu.worker_url,
                token=get_secret(updated.gpu.worker_token_secret),
                worker_id=updated.gpu.worker_id,
                transport=updated.gpu.transport,
            )
        clear_capability_cache()
        return {
            "ok": True,
            "gpu": updated.gpu.model_dump(mode="json"),
            "status": compute_status(settings=updated),
        }

    @app.post("/api/v1/gpu/unload")
    def gpu_unload(payload: GpuUnloadRequest | None = None) -> dict[str, Any]:
        settings = _current()
        router = _require_router(settings)
        try:
            result = router.client.unload_models((payload or GpuUnloadRequest()).name)
        except Exception as exc:  # noqa: BLE001 - surface worker errors as HTTP
            raise HTTPException(
                status_code=502,
                detail={"ok": False, "code": "gpu_unload_failed", "message": str(exc)},
            ) from exc
        return {"ok": True, "result": result}

    @app.post("/api/v1/gpu/shared/validate")
    def gpu_shared_validate(payload: GpuSharedRequest) -> dict[str, Any]:
        settings = _current()
        router = _require_router(settings)
        path = payload.path.strip() or "videoflow-probe.txt"
        try:
            result = router.client.validate_shared(path)
        except Exception as exc:  # noqa: BLE001 - surface worker errors as HTTP
            raise HTTPException(
                status_code=502,
                detail={
                    "ok": False,
                    "code": "shared_validate_failed",
                    "message": str(exc),
                },
            ) from exc
        return {"ok": True, "result": result}

    @app.post("/api/v1/gpu/benchmark")
    def gpu_benchmark() -> dict[str, Any]:
        settings = _current()
        router = _require_router(settings)
        started = time.perf_counter()
        health = router.health(force=True)
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return {
            "ok": health.available,
            "kind": "connectivity",
            "latency_ms": latency_ms,
            "speedup": None,
            "worker": health.model_dump(mode="json"),
        }


__all__ = [
    "GpuConnectRequest",
    "GpuSettingsPatch",
    "GpuSharedRequest",
    "GpuUnloadRequest",
    "WindowsKitRequest",
    "register_gpu_routes",
]
