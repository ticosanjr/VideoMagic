"""FastAPI application factory for the isolated GPU worker."""

from __future__ import annotations

import secrets
import shutil
import socket
import threading
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    JSONResponse,
)
from fastapi.staticfiles import StaticFiles

from gpu_worker import __version__
from gpu_worker.api_admin import register_admin_routes
from gpu_worker.api_common import PUBLIC_PATHS
from gpu_worker.api_jobs import register_job_routes
from gpu_worker.api_models import JobSubmission
from gpu_worker.api_uploads import register_upload_routes
from gpu_worker.artifacts import ArtifactStore
from gpu_worker.discovery import DiscoveryBeacon
from gpu_worker.doctor import dependency_report
from gpu_worker.gpu import detect_gpu
from gpu_worker.handlers import HandlerRegistry, build_default_registry
from gpu_worker.handlers_gpu import (
    warmup_models,
)
from gpu_worker.http_auth import (
    is_loopback_client as _is_loopback_client,
)
from gpu_worker.http_auth import (
    is_private_client as _is_private_client,
)
from gpu_worker.http_auth import (
    matches_allowlist as _matches_allowlist,
)
from gpu_worker.http_auth import (
    read_token_file as _read_token_file,
)
from gpu_worker.models import ModelRegistry
from gpu_worker.security import (
    is_job_id,
)
from gpu_worker.settings import Settings
from gpu_worker.store import JobRecord, JobStore
from gpu_worker.telemetry import (
    rotate_log as _rotate_log,
)
from gpu_worker.uploads import UploadStore
from gpu_worker.vram import VramBudget
from gpu_worker.worker import JobRunner

_SHA_CACHE: dict[tuple[str, int, int], str] = {}










def create_app(
    settings: Settings | None = None,
    *,
    registry: HandlerRegistry | None = None,
) -> FastAPI:
    """Build the worker app.

    Threads start immediately so plain ``TestClient(app)`` usage (without a lifespan
    context manager) still processes jobs; lifespan shutdown stops them idempotently.
    """

    config = settings or Settings.from_env()
    work_dir = Path(config.work_dir).expanduser().resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    token_path = work_dir / "worker.token"
    runtime_token = _read_token_file(token_path) or (config.token or "")
    shared_root = (
        Path(config.shared_root).expanduser().resolve() if config.shared_root is not None else None
    )

    store = JobStore(work_dir / "jobs.sqlite3")
    store.initialize()
    store.fail_interrupted_jobs()
    retention_sec = max(3600.0, float(config.job_retention_hours) * 3600.0)
    for stale_job in store.cleanup_finished(retention_sec):
        shutil.rmtree(work_dir / "jobs" / stale_job, ignore_errors=True)

    artifacts = ArtifactStore(work_dir / "artifacts", store, max_bytes=config.max_upload_bytes)
    uploads = UploadStore(
        work_dir / "uploads",
        artifacts,
        max_bytes=config.max_upload_bytes,
    )
    uploads.cleanup_stale()
    models = ModelRegistry(config.model_ttl_sec)
    vram = VramBudget(
        max_vram_mb=config.max_vram_mb,
        reserve_mb=config.vram_reserve_mb,
    )
    if registry is not None:
        handlers = registry
    else:
        try:
            handlers = build_default_registry(config, models)
        except Exception as exc:  # noqa: BLE001 - optional handlers cannot kill startup
            handlers = HandlerRegistry()
            handlers.mark_unavailable(
                "builtin_handlers",
                f"builtin handler init failed: {type(exc).__name__}: {exc}",
            )
    dependencies = dependency_report(config)
    runner = JobRunner(
        store=store,
        registry=handlers,
        artifacts=artifacts,
        work_dir=work_dir,
        shared_root=shared_root,
        models=models,
        vram=vram,
        cpu_workers=config.cpu_workers,
    )

    closed = threading.Event()

    def close() -> None:
        if closed.is_set():
            return
        closed.set()
        beacon = getattr(app.state, "beacon", None)
        maintenance_stop.set()
        if beacon is not None:
            beacon.stop()
        runner.stop()
        models.stop()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            close()

    app = FastAPI(
        title="VideoFlow GPU Worker",
        description="Isolated GPU inference worker for VideoFlow 2.90.",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = config
    app.state.work_dir = work_dir
    app.state.shared_root = shared_root
    app.state.store = store
    app.state.artifacts = artifacts
    app.state.uploads = uploads
    app.state.models = models
    app.state.dependencies = dependencies
    app.state.vram = vram
    app.state.registry = handlers
    app.state.runner = runner
    app.state.close = close
    app.state.shutdown = close
    app.state.register_handler = handlers.register_handler
    app.state.handlers = handlers
    app.state.job_store = store
    app.state.artifact_store = artifacts
    app.state.model_registry = models
    app.state.worker = runner
    app.state.started_at = time.time()
    app.state.last_request_at = 0.0
    app.state.last_request = {}
    app.state.runtime_token = runtime_token
    app.state.token_path = token_path
    app.state.audit = deque(maxlen=500)
    app.state.clients = {}
    app.state.request_count = 0
    app.state.history = deque(maxlen=360)
    app.state.firewall_cache = (0.0, {})
    app.state.warmup = {"running": False, "loaded": [], "skipped": [], "errors": []}
    warmup_lock = threading.Lock()
    maintenance_stop = threading.Event()
    app.state.maintenance_stop = maintenance_stop

    def audit(client: str, path: str, method: str, outcome: str) -> None:
        app.state.audit.append(
            {
                "at": time.time(),
                "client": client,
                "path": path,
                "method": method,
                "outcome": outcome,
            }
        )

    def run_warmup() -> dict[str, Any]:
        with warmup_lock:
            if app.state.warmup.get("running"):
                return dict(app.state.warmup)
            app.state.warmup = {
                "running": True,
                "loaded": [],
                "skipped": [],
                "errors": [],
                "started_at": time.time(),
            }
        result = warmup_models(config, models)
        with warmup_lock:
            app.state.warmup = {
                **result,
                "running": False,
                "finished_at": time.time(),
            }
        return dict(app.state.warmup)

    app.state.run_warmup = run_warmup

    def sample_history() -> dict[str, Any]:
        gpu = detect_gpu()
        metrics = runner.metrics()
        sample = {
            "at": time.time(),
            "gpu_utilization": gpu.gpu_utilization,
            "vram_free_mb": gpu.vram_free_mb,
            "vram_total_mb": gpu.vram_total_mb,
            "temperature_c": gpu.temperature_c,
            "queue_depth": store.queue_depth(),
            "running": len(metrics.get("current") or []),
            "completed": len(metrics.get("recent") or []),
        }
        app.state.history.append(sample)
        return sample

    def history_loop() -> None:
        while not maintenance_stop.wait(5.0):
            try:
                sample_history()
            except Exception:  # noqa: BLE001 - sampling is advisory
                continue

    def maintenance_loop() -> None:
        while not maintenance_stop.wait(3600.0):
            try:
                for stale_job in store.cleanup_finished(retention_sec):
                    shutil.rmtree(work_dir / "jobs" / stale_job, ignore_errors=True)
                artifacts.cleanup(store.referenced_artifact_ids())
                store.prune_metrics(config.metrics_retention_hours * 3600.0)
                _rotate_log(config)
            except Exception:  # noqa: BLE001 - maintenance must never kill the worker
                continue

    @app.middleware("http")
    async def require_token(request: Request, call_next):
        if request.url.path in PUBLIC_PATHS or request.url.path == "/health/":
            return await call_next(request)
        configured = str(app.state.runtime_token or "")
        supplied = request.headers.get("x-vf-token", "")
        valid = bool(
            configured
            and supplied
            and secrets.compare_digest(
                supplied.encode("utf-8"), configured.encode("utf-8")
            )
        )
        client_host = request.client.host if request.client else ""
        loopback = _is_loopback_client(client_host)
        lan_open = bool(
            app.state.settings.allow_lan_open
            and not app.state.settings.token_only
            and _is_private_client(client_host)
            and (
                not app.state.settings.allowed_clients
                or _matches_allowlist(client_host, app.state.settings.allowed_clients)
            )
        )
        if valid or lan_open or loopback:
            outcome = "token" if valid else ("loopback" if loopback else "lan_open")
            audit(client_host, request.url.path, request.method, outcome)
            app.state.request_count += 1
            app.state.clients[client_host] = time.time()
            if request.url.path not in {
                "/api/overview",
                "/api/jobs",
                "/api/logs",
                "/health",
                "/probe",
            } and not request.url.path.startswith("/ui"):
                app.state.last_request_at = time.time()
                app.state.last_request = {
                    "path": request.url.path,
                    "method": request.method,
                    "client": client_host,
                    "at": app.state.last_request_at,
                }
            return await call_next(request)
        audit(client_host, request.url.path, request.method, "denied")
        if not configured:
            return JSONResponse(
                status_code=503,
                content={"detail": "VF_GPU_TOKEN is not configured on the worker"},
            )
        return JSONResponse(
            status_code=401, content={"detail": "missing or invalid X-VF-Token"}
        )

    def require_job(job_id: str) -> JobRecord:
        if not is_job_id(job_id):
            raise HTTPException(status_code=404, detail="job not found")
        job = store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    ctx = SimpleNamespace(
        config=config,
        store=store,
        artifacts=artifacts,
        uploads=uploads,
        models=models,
        vram=vram,
        handlers=handlers,
        runner=runner,
        work_dir=work_dir,
        shared_root=shared_root,
        require_job=require_job,
        run_warmup=run_warmup,
        audit=audit,
    )
    register_admin_routes(app, ctx)
    register_upload_routes(app, ctx)
    register_job_routes(app, ctx)
    health = ctx.health

    ui_dir = Path(__file__).resolve().parent / "ui"
    if ui_dir.is_dir():
        app.mount("/ui", StaticFiles(directory=str(ui_dir), html=True), name="ui")

    runner.start()
    models.start()
    sample_history()
    threading.Thread(
        target=history_loop,
        name="gpu-worker-history",
        daemon=True,
    ).start()
    threading.Thread(
        target=maintenance_loop,
        name="gpu-worker-maintenance",
        daemon=True,
    ).start()
    if config.warmup and config.builtin_handlers:
        threading.Thread(
            target=run_warmup,
            name="gpu-worker-warmup",
            daemon=True,
        ).start()
    beacon: DiscoveryBeacon | None = None
    if config.discovery:
        beacon = DiscoveryBeacon(
            worker_id=config.worker_id or socket.gethostname(),
            port=config.port,
            advertise_port=config.advertise_port,
            health=health,
        )
        beacon.start()
        app.state.beacon = beacon
    return app


# Re-exported for callers that build the app themselves.
__all__ = ["JobSubmission", "create_app"]
