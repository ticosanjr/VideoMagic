"""FastAPI application factory for the isolated GPU worker."""

from __future__ import annotations

import secrets
import shutil
import threading
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from gpu_worker import __version__
from gpu_worker.artifacts import ArtifactStore, ArtifactTooLarge
from gpu_worker.gpu import detect_gpu
from gpu_worker.handlers import HandlerRegistry, build_default_registry
from gpu_worker.models import ModelRegistry
from gpu_worker.security import (
    UnsafePathError,
    is_artifact_id,
    is_capability,
    is_job_id,
    resolve_shared_path,
)
from gpu_worker.settings import Settings
from gpu_worker.store import JobRecord, JobStore
from gpu_worker.worker import JobRunner

MAX_JOB_INPUTS = 64
JOB_RETENTION_SEC = 7 * 24 * 3600
PUBLIC_PATHS = frozenset({"/health"})


class JobSubmission(BaseModel):
    """Request body for ``POST /jobs/{capability}``."""

    params: dict[str, Any] = Field(default_factory=dict)
    inputs: list[str] = Field(default_factory=list)
    shared: bool = False
    shared_inputs: list[str] = Field(default_factory=list)


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
    shared_root = (
        Path(config.shared_root).expanduser().resolve() if config.shared_root is not None else None
    )

    store = JobStore(work_dir / "jobs.sqlite3")
    store.initialize()
    store.fail_interrupted_jobs()
    for stale_job in store.cleanup_finished(JOB_RETENTION_SEC):
        shutil.rmtree(work_dir / "jobs" / stale_job, ignore_errors=True)

    artifacts = ArtifactStore(work_dir / "artifacts", store, max_bytes=config.max_upload_bytes)
    models = ModelRegistry(config.model_ttl_sec)
    handlers = registry or build_default_registry(config)
    runner = JobRunner(
        store=store,
        registry=handlers,
        artifacts=artifacts,
        work_dir=work_dir,
        shared_root=shared_root,
    )

    closed = threading.Event()

    def close() -> None:
        if closed.is_set():
            return
        closed.set()
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
    app.state.models = models
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

    @app.middleware("http")
    async def require_token(request: Request, call_next):
        if request.url.path in PUBLIC_PATHS or request.url.path == "/health/":
            return await call_next(request)
        configured = app.state.settings.token
        if not configured:
            return JSONResponse(
                status_code=503,
                content={"detail": "VF_GPU_TOKEN is not configured on the worker"},
            )
        supplied = request.headers.get("x-vf-token", "")
        valid = supplied and secrets.compare_digest(
            supplied.encode("utf-8"), configured.encode("utf-8")
        )
        if not valid:
            return JSONResponse(
                status_code=401, content={"detail": "missing or invalid X-VF-Token"}
            )
        return await call_next(request)

    def require_job(job_id: str) -> JobRecord:
        if not is_job_id(job_id):
            raise HTTPException(status_code=404, detail="job not found")
        job = store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    @app.get("/health")
    def health() -> dict[str, Any]:
        gpu = detect_gpu()
        model_details = models.snapshot()
        return {
            "status": "ok",
            "version": __version__,
            "available": True,
            "gpu_available": gpu.available,
            "gpu_name": gpu.name,
            "vram_free_mb": gpu.vram_free_mb,
            "vram_total_mb": gpu.vram_total_mb,
            "capabilities": handlers.available(),
            "unavailable_capabilities": handlers.unavailable(),
            "models": [model["name"] for model in model_details],
            "model_details": model_details,
            "queue_depth": store.queue_depth(),
        }

    @app.post("/artifacts")
    async def upload_artifact(
        file: Annotated[UploadFile, File()],
    ) -> dict[str, Any]:
        try:
            record = await run_in_threadpool(artifacts.save_upload, file.file, file.filename)
        except ArtifactTooLarge as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except UnsafePathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            await file.close()
        return {"artifact_id": record.id, "sha256": record.id, "bytes": record.size}

    @app.post("/jobs/{capability}")
    def submit_job(capability: str, body: JobSubmission) -> dict[str, Any]:
        if not is_capability(capability) or not handlers.has_capability(capability):
            raise HTTPException(status_code=404, detail=f"unknown capability: {capability}")
        if not handlers.is_available(capability):
            reason = handlers.reason(capability)
            raise HTTPException(
                status_code=501,
                detail=f"capability '{capability}' is unavailable: {reason}",
            )
        if len(body.inputs) > MAX_JOB_INPUTS or len(body.shared_inputs) > MAX_JOB_INPUTS:
            raise HTTPException(
                status_code=400,
                detail=f"at most {MAX_JOB_INPUTS} inputs are allowed per job",
            )

        inputs: list[str] = []
        for artifact_id in body.inputs:
            if not is_artifact_id(artifact_id):
                raise HTTPException(status_code=400, detail=f"invalid artifact id: {artifact_id}")
            if artifacts.get(artifact_id) is None:
                raise HTTPException(status_code=400, detail=f"unknown artifact id: {artifact_id}")
            inputs.append(artifact_id)

        if body.shared_inputs:
            if not body.shared:
                raise HTTPException(status_code=400, detail="shared_inputs requires shared=true")
            if shared_root is None:
                raise HTTPException(status_code=400, detail="VF_GPU_SHARED_ROOT is not configured")
            for relative in body.shared_inputs:
                try:
                    resolve_shared_path(shared_root, relative)
                except UnsafePathError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
        elif body.shared and shared_root is None:
            raise HTTPException(status_code=400, detail="VF_GPU_SHARED_ROOT is not configured")

        if store.queue_depth() >= config.max_queue:
            raise HTTPException(
                status_code=429,
                detail="job queue is full",
                headers={"Retry-After": "5"},
            )

        job_id = uuid.uuid4().hex
        store.create_job(
            job_id=job_id,
            capability=capability,
            params=body.params,
            inputs=inputs,
            shared_inputs=list(body.shared_inputs),
        )
        if not runner.submit(job_id):
            store.delete_job(job_id)
            raise HTTPException(status_code=503, detail="worker is shutting down")
        return {"job_id": job_id, "status": "queued"}

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        return require_job(job_id).as_dict()

    @app.get("/jobs/{job_id}/artifact/{name}")
    def download_artifact(job_id: str, name: str) -> FileResponse:
        job = require_job(job_id)
        if name not in job.artifacts:
            raise HTTPException(status_code=404, detail="artifact not found")
        directory = (work_dir / "jobs" / job.id / "artifacts").resolve()
        path = (directory / name).resolve()
        if path.parent != directory or not path.is_file():
            raise HTTPException(status_code=404, detail="artifact not found")
        return FileResponse(path, media_type="application/octet-stream", filename=name)

    @app.delete("/jobs/{job_id}")
    def delete_job(job_id: str) -> dict[str, Any]:
        job = require_job(job_id)
        store.delete_job(job.id)
        shutil.rmtree(work_dir / "jobs" / job.id, ignore_errors=True)
        return {"job_id": job.id, "deleted": True}

    runner.start()
    models.start()
    return app


# Re-exported for callers that build the app themselves.
__all__ = ["JobSubmission", "create_app"]
