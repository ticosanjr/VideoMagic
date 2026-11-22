"""Probe, job submission, artifact download and maintenance routes."""

from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse

from gpu_worker.api_common import MAX_JOB_INPUTS, _parse_range, _sha256_cached
from gpu_worker.api_models import JobSubmission
from gpu_worker.doctor import dependency_report
from gpu_worker.gpu import detect_gpu
from gpu_worker.gpu_handlers import probe_nvenc
from gpu_worker.security import (
    UnsafePathError,
    is_artifact_id,
    is_capability,
    resolve_shared_output,
    resolve_shared_path,
)
from gpu_worker.store import JobRecord
from gpu_worker.telemetry import disk_free_mb as _disk_free_mb


def register_job_routes(app: FastAPI, ctx: Any) -> None:
    config = ctx.config
    store = ctx.store
    artifacts = ctx.artifacts
    models = ctx.models
    handlers = ctx.handlers
    runner = ctx.runner
    work_dir = ctx.work_dir
    shared_root = ctx.shared_root
    require_job = ctx.require_job

    @app.post("/probe")
    def probe() -> dict[str, Any]:
        started = time.perf_counter()
        gpu = detect_gpu()
        ffmpeg = config.ffmpeg_cmd or "ffmpeg"
        # Benchmark must re-test the driver, not replay a cached startup result.
        nvenc_probe = probe_nvenc(ffmpeg, force=True)
        nvenc = nvenc_probe.available
        dependencies = dependency_report(config, force=True)
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
        app.state.dependencies = dependencies
        return {
            "ok": bool(gpu.available and nvenc),
            "cuda": bool(gpu.available),
            "nvenc": bool(nvenc),
            "nvenc_error": nvenc_probe.reason,
            "nvenc_advice": nvenc_probe.advice,
            "nvenc_args": list(nvenc_probe.args),
            "asr_ready": bool(dependencies.get("asr_ready")),
            "asr_error": str(dependencies.get("asr_error") or ""),
            "dependencies": dependencies,
            "asr": bool(dependencies.get("asr_ready") and ct2_devices > 0),
            "asr_vad_ready": bool(dependencies.get("asr_vad_ready")),
            "asr_vad_error": str(dependencies.get("asr_vad_error") or ""),
            "matte": bool(dependencies.get("matte_ready")),
            "repair_hint": str(dependencies.get("repair_hint") or ""),
            "gpu_name": gpu.name,
            "vram_free_mb": gpu.vram_free_mb,
            "ct2_devices": ct2_devices,
            "providers": providers,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
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
