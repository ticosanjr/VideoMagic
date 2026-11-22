"""Worker health, diagnostics, security and operations routes."""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import time
from contextlib import suppress
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from gpu_worker import __version__
from gpu_worker.doctor import dependency_report
from gpu_worker.gpu import detect_gpu
from gpu_worker.handlers_gpu import probe_nvenc
from gpu_worker.http_auth import is_loopback_client as _is_loopback_client
from gpu_worker.telemetry import current_job as _current_job
from gpu_worker.telemetry import disk_free_mb as _disk_free_mb
from gpu_worker.telemetry import lan_urls as _lan_urls
from gpu_worker.telemetry import local_ip as _local_ip
from gpu_worker.telemetry import log_path as _log_path
from gpu_worker.telemetry import tail_log as _tail_log


def register_admin_routes(app: FastAPI, ctx: Any) -> None:
    config = ctx.config
    store = ctx.store
    models = ctx.models
    vram = ctx.vram
    handlers = ctx.handlers
    runner = ctx.runner
    work_dir = ctx.work_dir
    shared_root = ctx.shared_root
    run_warmup = ctx.run_warmup
    audit = ctx.audit

    @app.get("/health")
    def health() -> dict[str, Any]:
        gpu = detect_gpu()
        nvenc_probe = probe_nvenc(config.ffmpeg_cmd or "ffmpeg")
        model_details = models.snapshot()
        hostname = socket.gethostname()
        return {
            "status": "ok",
            "version": __version__,
            "available": True,
            "asr_ready": bool(app.state.dependencies.get("asr_ready")),
            "asr_error": str(app.state.dependencies.get("asr_error") or ""),
            "asr_vad_ready": bool(app.state.dependencies.get("asr_vad_ready")),
            "matte_ready": bool(app.state.dependencies.get("matte_ready")),
            "repair_hint": str(app.state.dependencies.get("repair_hint") or ""),
            "dependencies": app.state.dependencies,
            "worker_id": config.worker_id or hostname,
            "hostname": hostname,
            "ip_local": _local_ip(),
            "port": config.port,
            "platform": "windows" if os.name == "nt" else "linux",
            "shared_root": str(shared_root) if shared_root is not None else "",
            "gpu_available": gpu.available,
            "gpu_name": gpu.name,
            "vram_free_mb": gpu.vram_free_mb,
            "vram_total_mb": gpu.vram_total_mb,
            "vram_used_mb": gpu.vram_used_mb,
            "vram_budget_mb": vram.budget_mb(),
            "gpu_utilization": gpu.gpu_utilization,
            "temperature_c": gpu.temperature_c,
            "driver_version": getattr(gpu, "driver_version", ""),
            "capabilities": handlers.available(),
            "unavailable_capabilities": handlers.unavailable(),
            "auth_mode": (
                "token_only"
                if config.token_only
                else (
                    "lan_open"
                    if config.allow_lan_open
                    else ("token" if app.state.runtime_token else "none")
                )
            ),
            "token_configured": bool(app.state.runtime_token),
            "token_only": config.token_only,
            "allowed_clients": list(config.allowed_clients),
            "nvenc": nvenc_probe.available,
            "encoder": "nvenc" if nvenc_probe.available else "libx264",
            "models": [model["name"] for model in model_details],
            "model_details": model_details,
            "queue_depth": store.queue_depth(),
            "uptime_sec": round(max(0.0, time.time() - app.state.started_at), 1),
            "current_job": _current_job(store),
            "last_request": app.state.last_request,
            "nvenc_error": nvenc_probe.reason,
            "nvenc_advice": nvenc_probe.advice,
            "nvenc_args": list(nvenc_probe.args),
            "lan_urls": _lan_urls(),
            "disk_free_mb": _disk_free_mb(work_dir),
            "min_free_disk_mb": config.min_free_disk_mb,
            "warmup": dict(app.state.warmup),
            "job_retention_hours": config.job_retention_hours,
            "clients_connected": len(app.state.clients),
            "request_count": app.state.request_count,
        }

    @app.get("/api/overview")
    def api_overview() -> dict[str, Any]:
        return {
            "ok": True,
            "health": health(),
            "jobs": [job.summary() for job in store.list_jobs(limit=12)],
            "runner": runner.metrics(),
            "warmup": dict(app.state.warmup),
            "logs": _tail_log(config, limit=40),
        }

    @app.get("/api/doctor")
    def api_doctor() -> dict[str, Any]:
        report = dependency_report(config, force=True)
        app.state.dependencies = report
        return {"ok": report.get("ok", False), **report}

    @app.post("/api/warmup")
    def api_warmup() -> dict[str, Any]:
        if not config.builtin_handlers:
            raise HTTPException(
                status_code=409,
                detail="warmup requires VF_GPU_BUILTIN_HANDLERS=1",
            )
        return {"ok": True, **run_warmup()}

    @app.get("/api/jobs")
    def api_jobs(limit: int = 25) -> dict[str, Any]:
        return {
            "ok": True,
            "jobs": [job.summary() for job in store.list_jobs(limit=limit)],
        }

    @app.get("/api/logs")
    def api_logs(lines: int = 200) -> dict[str, Any]:
        return {"ok": True, "text": _tail_log(config, limit=max(1, min(lines, 2000)))}

    def firewall_status() -> dict[str, Any]:
        cached_at, cached = app.state.firewall_cache
        if cached and time.time() - cached_at < 60.0:
            return cached
        if os.name != "nt":
            payload = {"supported": False, "rules": []}
        else:
            command = (
                "Get-NetFirewallRule -DisplayName 'VideoFlow GPU Worker*' "
                "| Select-Object DisplayName,Enabled,Direction,Action,Profile "
                "| ConvertTo-Json -Compress"
            )
            try:
                completed = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", command],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                raw = json.loads(completed.stdout or "null")
                rules = raw if isinstance(raw, list) else ([raw] if raw else [])
                payload = {"supported": True, "rules": rules}
            except Exception as exc:  # noqa: BLE001 - firewall is advisory
                payload = {"supported": True, "rules": [], "error": str(exc)}
        app.state.firewall_cache = (time.time(), payload)
        return payload

    @app.get("/api/history")
    def api_history(limit: int = 120) -> dict[str, Any]:
        return {
            "ok": True,
            "samples": list(app.state.history),
            "metrics": store.metrics_history(limit=max(1, min(limit, 1000))),
        }

    @app.get("/api/system")
    def api_system(request: Request) -> dict[str, Any]:
        clients = [
            {"client": host, "last_seen": seen}
            for host, seen in sorted(
                app.state.clients.items(), key=lambda item: item[1], reverse=True
            )
        ]
        return {
            "ok": True,
            "version": __version__,
            "uptime_sec": round(max(0.0, time.time() - app.state.started_at), 1),
            "disk_free_mb": _disk_free_mb(work_dir),
            "queue_depth": store.queue_depth(),
            "clients": clients,
            "request_count": app.state.request_count,
            "token_only": config.token_only,
            "allowed_clients": list(config.allowed_clients),
            "firewall": firewall_status(),
            "log_path": str(_log_path(config)),
            "token_file": str(app.state.token_path),
            "history": list(app.state.history),
            "audit": (
                list(app.state.audit)[-5:]
                if _is_loopback_client(request.client.host if request.client else "")
                else []
            ),
        }

    @app.get("/api/security")
    def api_security(request: Request) -> dict[str, Any]:
        if not _is_loopback_client(request.client.host if request.client else ""):
            raise HTTPException(status_code=403, detail="local access only")
        return {
            "ok": True,
            "auth_mode": (
                "token_only"
                if config.token_only
                else ("lan_open" if config.allow_lan_open else "token")
            ),
            "token_configured": bool(app.state.runtime_token),
            "token_only": config.token_only,
            "allow_lan_open": config.allow_lan_open,
            "allowed_clients": list(config.allowed_clients),
            "token_file": str(app.state.token_path),
        }

    @app.get("/api/audit")
    def api_audit(request: Request, limit: int = 100) -> dict[str, Any]:
        if not _is_loopback_client(request.client.host if request.client else ""):
            raise HTTPException(status_code=403, detail="local access only")
        entries = list(app.state.audit)[-max(1, min(int(limit), 500)) :]
        return {"ok": True, "entries": entries}

    @app.post("/api/token/rotate")
    def api_token_rotate(request: Request) -> dict[str, Any]:
        if not _is_loopback_client(request.client.host if request.client else ""):
            raise HTTPException(status_code=403, detail="local access only")
        token = secrets.token_urlsafe(32)
        try:
            app.state.token_path.write_text(token + "\n", encoding="utf-8")
            with suppress(OSError):
                os.chmod(app.state.token_path, 0o600)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"cannot write token: {exc}") from exc
        app.state.runtime_token = token
        audit(
            request.client.host if request.client else "",
            "/api/token/rotate",
            "POST",
            "rotated",
        )
        return {"ok": True, "token": token, "token_file": str(app.state.token_path)}

    @app.post("/api/restart")
    def api_restart(request: Request) -> dict[str, Any]:
        if not _is_loopback_client(request.client.host if request.client else ""):
            raise HTTPException(status_code=403, detail="local access only")
        runner.restart()
        return {"ok": True, "runner": runner.metrics()}

    @app.post("/api/open-logs")
    def api_open_logs(request: Request) -> dict[str, Any]:
        if not _is_loopback_client(request.client.host if request.client else ""):
            raise HTTPException(status_code=403, detail="local access only")
        target = _log_path(config)
        if not target.exists():
            target = target.parent
        try:
            if os.name == "nt":
                os.startfile(str(target))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception as exc:  # noqa: BLE001 - desktop integration is optional
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "path": str(target)}

    @app.get("/")
    def ui_root() -> RedirectResponse:
        return RedirectResponse(url="/ui/")

    ctx.health = health
