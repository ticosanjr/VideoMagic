"""FastAPI application factory for the isolated GPU worker."""

from __future__ import annotations

import shutil
import socket
import threading
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from gpu_worker import __version__
from gpu_worker.api_admin import register_admin_routes
from gpu_worker.api_background import install_background
from gpu_worker.api_common import make_require_job
from gpu_worker.api_jobs import register_job_routes
from gpu_worker.api_middleware import install_auth_middleware
from gpu_worker.api_models import JobSubmission
from gpu_worker.api_uploads import register_upload_routes
from gpu_worker.artifacts import ArtifactStore
from gpu_worker.discovery import DiscoveryBeacon
from gpu_worker.doctor import dependency_report
from gpu_worker.handlers import HandlerRegistry, build_default_registry
from gpu_worker.http_auth import (
    read_token_file as _read_token_file,
)
from gpu_worker.models import ModelRegistry
from gpu_worker.settings import Settings
from gpu_worker.store import JobStore
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
    maintenance_stop = threading.Event()
    app.state.maintenance_stop = maintenance_stop

    background = install_background(
        app,
        config=config,
        store=store,
        artifacts=artifacts,
        models=models,
        runner=runner,
        work_dir=work_dir,
        maintenance_stop=maintenance_stop,
        retention_sec=retention_sec,
    )
    require_job = make_require_job(store)
    install_auth_middleware(app, background.audit)

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
        run_warmup=background.run_warmup,
        audit=background.audit,
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
    background.start()
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
