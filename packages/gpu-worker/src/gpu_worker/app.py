"""FastAPI application factory for the isolated GPU worker."""

from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from gpu_worker import __version__
from gpu_worker.artifacts import ArtifactStore, ArtifactTooLarge
from gpu_worker.discovery import DiscoveryBeacon
from gpu_worker.gpu import detect_gpu
from gpu_worker.handlers import HandlerRegistry, build_default_registry
from gpu_worker.handlers_gpu import nvenc_available, nvenc_error, warmup_models
from gpu_worker.models import ModelRegistry
from gpu_worker.security import (
    UnsafePathError,
    is_artifact_id,
    is_capability,
    is_job_id,
    resolve_shared_output,
    resolve_shared_path,
)
from gpu_worker.settings import Settings
from gpu_worker.store import JobRecord, JobStore
from gpu_worker.uploads import UploadStore
from gpu_worker.vram import VramBudget
from gpu_worker.worker import JobRunner

MAX_JOB_INPUTS = 64
PUBLIC_PATHS = frozenset({"/health"})


def _is_private_client(host: str | None) -> bool:
    try:
        address = ipaddress.ip_address(str(host or ""))
    except ValueError:
        return False
    return bool(address.is_private or address.is_loopback)


def _is_loopback_client(host: str | None) -> bool:
    try:
        return ipaddress.ip_address(str(host or "")).is_loopback
    except ValueError:
        return False


def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            return str(probe.getsockname()[0])
    except OSError:
        return "127.0.0.1"


_SHA_CACHE: dict[tuple[str, int, int], str] = {}
_SHA_LOCK = threading.Lock()


def _sha256_cached(path: Path) -> str:
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    with _SHA_LOCK:
        cached = _SHA_CACHE.get(key)
    if cached is not None:
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    with _SHA_LOCK:
        _SHA_CACHE[key] = value
    return value


def _parse_range(value: str, size: int) -> tuple[int, int] | None:
    text = str(value or "").strip()
    if not text.lower().startswith("bytes="):
        return None
    spec = text[6:].split(",", 1)[0].strip()
    if "-" not in spec:
        return None
    start_text, end_text = spec.split("-", 1)
    try:
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
        else:
            suffix = int(end_text)
            if suffix <= 0:
                return None
            start = max(0, size - suffix)
            end = size - 1
    except ValueError:
        return None
    if start < 0 or end < start or start >= size:
        return None
    return start, min(end, size - 1)


class UploadInit(BaseModel):
    """Request body for a resumable upload."""

    filename: str = "upload.bin"
    size: int = Field(ge=0)
    sha256: str = ""
    chunk_size: int = Field(default=8 * 1024 * 1024, ge=1, le=64 * 1024 * 1024)


class JobSubmission(BaseModel):
    """Request body for ``POST /jobs/{capability}``."""

    params: dict[str, Any] = Field(default_factory=dict)
    inputs: list[str] = Field(default_factory=list)
    shared: bool = False
    shared_inputs: list[str] = Field(default_factory=list)
    shared_outputs: list[str] = Field(default_factory=list)
    priority: int = Field(default=0, ge=-100, le=100)


def _current_job(store: JobStore) -> dict[str, Any] | None:
    for job in store.list_jobs(limit=10):
        if job.status in {"queued", "running"}:
            return job.summary()
    return None


def _lan_urls() -> list[str]:
    urls: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            address = str(info[4][0])
            if address.startswith("127.") or address in urls:
                continue
            urls.append(address)
    except OSError:
        pass
    local = _local_ip()
    if local and not local.startswith("127.") and local not in urls:
        urls.insert(0, local)
    return urls


def _disk_free_mb(path: Path) -> int:
    try:
        return int(shutil.disk_usage(path).free // (1024 * 1024))
    except OSError:
        return 0


def _log_path(config: Settings) -> Path:
    explicit = os.environ.get("VF_GPU_LOG_FILE", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    return Path(config.work_dir) / "worker.log"


def _tail_log(config: Settings, *, limit: int = 200) -> str:
    path = _log_path(config)
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-limit:])


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
    handlers = registry or build_default_registry(config)
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
    app.state.warmup = {"running": False, "loaded": [], "skipped": [], "errors": []}
    warmup_lock = threading.Lock()
    maintenance_stop = threading.Event()
    app.state.maintenance_stop = maintenance_stop

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
        result = warmup_models(config, handlers)
        with warmup_lock:
            app.state.warmup = {
                **result,
                "running": False,
                "finished_at": time.time(),
            }
        return dict(app.state.warmup)

    app.state.run_warmup = run_warmup

    def maintenance_loop() -> None:
        while not maintenance_stop.wait(3600.0):
            try:
                for stale_job in store.cleanup_finished(retention_sec):
                    shutil.rmtree(work_dir / "jobs" / stale_job, ignore_errors=True)
            except Exception:  # noqa: BLE001 - maintenance must never kill the worker
                continue

    @app.middleware("http")
    async def require_token(request: Request, call_next):
        if request.url.path in PUBLIC_PATHS or request.url.path == "/health/":
            return await call_next(request)
        configured = app.state.settings.token
        supplied = request.headers.get("x-vf-token", "")
        valid = bool(
            configured
            and supplied
            and secrets.compare_digest(
                supplied.encode("utf-8"), configured.encode("utf-8")
            )
        )
        client_host = request.client.host if request.client else ""
        lan_open = bool(
            app.state.settings.allow_lan_open and _is_private_client(client_host)
        )
        if valid or lan_open or _is_loopback_client(client_host):
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

    @app.get("/health")
    def health() -> dict[str, Any]:
        gpu = detect_gpu()
        model_details = models.snapshot()
        hostname = socket.gethostname()
        return {
            "status": "ok",
            "version": __version__,
            "available": True,
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
                "lan_open"
                if config.allow_lan_open
                else ("token" if config.token else "none")
            ),
            "nvenc": nvenc_available(config.ffmpeg_cmd or "ffmpeg"),
            "encoder": (
                "nvenc"
                if nvenc_available(config.ffmpeg_cmd or "ffmpeg")
                else "libx264"
            ),
            "models": [model["name"] for model in model_details],
            "model_details": model_details,
            "queue_depth": store.queue_depth(),
            "uptime_sec": round(max(0.0, time.time() - app.state.started_at), 1),
            "current_job": _current_job(store),
            "last_request": app.state.last_request,
            "nvenc_error": nvenc_error(config.ffmpeg_cmd or "ffmpeg"),
            "lan_urls": _lan_urls(),
            "disk_free_mb": _disk_free_mb(work_dir),
            "min_free_disk_mb": config.min_free_disk_mb,
            "warmup": dict(app.state.warmup),
            "job_retention_hours": config.job_retention_hours,
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

    @app.post("/probe")
    def probe() -> dict[str, Any]:
        started = time.perf_counter()
        gpu = detect_gpu()
        ffmpeg = config.ffmpeg_cmd or "ffmpeg"
        nvenc = nvenc_available(ffmpeg)
        ct2_devices = 0
        try:
            import ctranslate2

            ct2_devices = int(ctranslate2.get_cuda_device_count())
        except Exception:  # noqa: BLE001 - optional runtime
            ct2_devices = 0
        providers: list[str] = []
        try:
            import onnxruntime

            providers = [str(item) for item in onnxruntime.get_available_providers()]
        except Exception:  # noqa: BLE001 - optional runtime
            providers = []
        return {
            "ok": bool(gpu.available and nvenc),
            "cuda": bool(gpu.available),
            "nvenc": bool(nvenc),
            "asr": bool(gpu.available and ct2_devices > 0),
            "matte": "CUDAExecutionProvider" in providers,
            "gpu_name": gpu.name,
            "vram_free_mb": gpu.vram_free_mb,
            "ct2_devices": ct2_devices,
            "providers": providers,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
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

    @app.post("/artifacts/init")
    def init_artifact(body: UploadInit) -> dict[str, Any]:
        existing = artifacts.get(body.sha256) if body.sha256 else None
        if existing is not None:
            return {
                "upload_id": f"artifact:{existing.id}",
                "offset": existing.size,
                "size": existing.size,
                "chunk_size": body.chunk_size,
                "sha256": existing.id,
                "artifact_id": existing.id,
                "complete": True,
            }
        try:
            session = uploads.create(
                filename=body.filename,
                size=body.size,
                sha256=body.sha256,
                chunk_size=body.chunk_size,
            )
        except ArtifactTooLarge as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "upload_id": session.id,
            "offset": session.received,
            "size": session.size,
            "chunk_size": session.chunk_size,
            "sha256": session.sha256,
        }

    @app.patch("/artifacts/{upload_id}")
    async def append_artifact(upload_id: str, request: Request) -> dict[str, Any]:
        session = uploads.get(upload_id)
        if session is None:
            raise HTTPException(status_code=404, detail="upload session not found")
        content_range = request.headers.get("content-range", "")
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range.strip())
        if match is None:
            raise HTTPException(
                status_code=400,
                detail="Content-Range must be 'bytes start-end/total'",
            )
        start, end, total = (int(part) for part in match.groups())
        if total != session.size:
            raise HTTPException(status_code=400, detail="Content-Range total mismatch")
        if end < start or end >= session.size:
            raise HTTPException(status_code=400, detail="Content-Range is outside the upload")
        data = await request.body()
        if len(data) != end - start + 1:
            raise HTTPException(
                status_code=400,
                detail="Content-Range length does not match the request body",
            )
        try:
            updated = await run_in_threadpool(uploads.append, upload_id, start, data)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "upload_id": updated.id,
            "received": updated.received,
            "size": updated.size,
        }

    @app.post("/artifacts/{upload_id}/complete")
    async def complete_artifact(upload_id: str) -> dict[str, Any]:
        try:
            record = await run_in_threadpool(uploads.complete, upload_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ArtifactTooLarge as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "artifact_id": record.id,
            "sha256": record.id,
            "bytes": record.size,
            "filename": record.filename,
        }

    @app.get("/artifacts/{upload_id}/status")
    def artifact_upload_status(upload_id: str) -> dict[str, Any]:
        session = uploads.get(upload_id)
        if session is None:
            raise HTTPException(status_code=404, detail="upload session not found")
        return {
            "upload_id": session.id,
            "received": session.received,
            "size": session.size,
            "chunk_size": session.chunk_size,
            "sha256": session.sha256,
        }

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
        if len(body.shared_outputs) > MAX_JOB_INPUTS:
            raise HTTPException(
                status_code=400,
                detail=f"at most {MAX_JOB_INPUTS} outputs are allowed per job",
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

        if body.shared_outputs:
            if not body.shared:
                raise HTTPException(status_code=400, detail="shared_outputs requires shared=true")
            if shared_root is None:
                raise HTTPException(status_code=400, detail="VF_GPU_SHARED_ROOT is not configured")
            for relative in body.shared_outputs:
                try:
                    resolve_shared_output(shared_root, relative)
                except UnsafePathError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

        free_mb = _disk_free_mb(work_dir)
        if free_mb < config.min_free_disk_mb:
            raise HTTPException(
                status_code=507,
                detail=(
                    f"worker disk is low: {free_mb} MB free, "
                    f"minimum {config.min_free_disk_mb} MB"
                ),
            )
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
            shared_outputs=list(body.shared_outputs),
            priority=int(body.priority),
        )
        if not runner.submit(job_id, priority=int(body.priority)):
            store.delete_job(job_id)
            raise HTTPException(status_code=503, detail="worker is shutting down")
        return {"job_id": job_id, "status": "queued"}

    def artifact_path(job: JobRecord, name: str) -> Path:
        if name not in job.artifacts:
            raise HTTPException(status_code=404, detail="artifact not found")
        directory = (work_dir / "jobs" / job.id / "artifacts").resolve()
        path = (directory / name).resolve()
        if path.parent != directory or not path.is_file():
            raise HTTPException(status_code=404, detail="artifact not found")
        return path

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        return require_job(job_id).as_dict()

    @app.get("/jobs/{job_id}/artifacts")
    def list_job_artifacts(job_id: str) -> dict[str, Any]:
        job = require_job(job_id)
        items: list[dict[str, Any]] = []
        for name in job.artifacts:
            try:
                path = artifact_path(job, name)
            except HTTPException:
                continue
            items.append(
                {
                    "name": name,
                    "size": path.stat().st_size,
                    "sha256": _sha256_cached(path),
                }
            )
        return {"job_id": job.id, "artifacts": items}

    @app.head("/jobs/{job_id}/artifact/{name}")
    def head_artifact(job_id: str, name: str) -> Response:
        job = require_job(job_id)
        path = artifact_path(job, name)
        digest = _sha256_cached(path)
        headers = {
            "Content-Length": str(path.stat().st_size),
            "Accept-Ranges": "bytes",
            "X-VF-Sha256": digest,
            "ETag": f'"{digest}"',
        }
        return Response(
            status_code=200,
            media_type="application/octet-stream",
            headers=headers,
        )

    @app.get("/jobs/{job_id}/artifact/{name}")
    def download_artifact(job_id: str, name: str, request: Request) -> Response:
        job = require_job(job_id)
        path = artifact_path(job, name)
        size = path.stat().st_size
        digest = _sha256_cached(path)
        range_header = request.headers.get("range", "")
        if not range_header:
            return FileResponse(
                path,
                media_type="application/octet-stream",
                filename=name,
                headers={
                    "Accept-Ranges": "bytes",
                    "X-VF-Sha256": digest,
                    "ETag": f'"{digest}"',
                },
            )
        parsed = _parse_range(range_header, size)
        if parsed is None:
            return Response(
                status_code=416,
                headers={"Content-Range": f"bytes */{size}"},
            )
        start, end = parsed
        length = end - start + 1

        def chunks() -> Any:
            with path.open("rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = handle.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        headers = {
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(length),
            "Accept-Ranges": "bytes",
            "X-VF-Sha256": digest,
            "ETag": f'"{digest}"',
        }
        return StreamingResponse(
            chunks(),
            status_code=206,
            media_type="application/octet-stream",
            headers=headers,
        )

    @app.delete("/jobs/{job_id}")
    def delete_job(job_id: str) -> dict[str, Any]:
        job = require_job(job_id)
        store.delete_job(job.id)
        shutil.rmtree(work_dir / "jobs" / job.id, ignore_errors=True)
        return {"job_id": job.id, "deleted": True}

    @app.post("/models/unload")
    def unload_models(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        requested = str((payload or {}).get("name") or "").strip()
        if requested:
            removed = [requested] if models.unload(requested) else []
        else:
            removed = [item["name"] for item in models.snapshot() if models.unload(item["name"])]
        return {
            "unloaded": removed,
            "vram_used_mb": models.vram_used_mb(),
            "loaded_models": [item["name"] for item in models.snapshot()],
        }

    @app.post("/shared/validate")
    def validate_shared(payload: dict[str, Any]) -> dict[str, Any]:
        if shared_root is None:
            raise HTTPException(status_code=400, detail="VF_GPU_SHARED_ROOT is not configured")
        relative = str(payload.get("path") or "").strip()
        try:
            target = resolve_shared_output(shared_root, relative)
            probe = target.with_name(f".{target.name}.probe")
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except (OSError, UnsafePathError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "path": relative, "resolved": str(target)}

    ui_dir = Path(__file__).resolve().parent / "ui"
    if ui_dir.is_dir():
        app.mount("/ui", StaticFiles(directory=str(ui_dir), html=True), name="ui")

    runner.start()
    models.start()
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
