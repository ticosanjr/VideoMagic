"""Project and job routes for the local API."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from videoflow import __version__
from videoflow.application.jobs import TERMINAL, JobManager
from videoflow.domain.errors import VideoFlowError
from videoflow.domain.paths import resolve_allowed
from videoflow.runtime import allowed_roots, find_binary, portable_home


class NewJobRequest(BaseModel):
    source: str = Field(min_length=1)
    output: str = Field(min_length=1)
    noise_db: float = -30.0
    min_silence_ms: int = Field(default=400, ge=0)
    jcut: bool = True
    lcut: bool = False
    zooms: bool = True
    dialect: Literal["1.9", "1.10"] = "1.9"
    transcript: str | None = None
    cull_retakes: bool = False


def register_routes(app: FastAPI, jobs: JobManager) -> None:
    @app.post("/api/v1/jobs", status_code=202)
    def create_job(request: NewJobRequest) -> dict[str, object]:
        roots = allowed_roots()
        try:
            source = resolve_allowed(Path(request.source), roots)
            output = resolve_allowed(Path(request.output), roots)
            transcript = (
                resolve_allowed(Path(request.transcript), roots) if request.transcript else None
            )
            job = jobs.start(
                source,
                output,
                options={
                    "noise_db": request.noise_db,
                    "min_silence_ms": request.min_silence_ms,
                    "jcut": request.jcut,
                    "lcut": request.lcut,
                    "zooms": request.zooms,
                    "dialect": request.dialect,
                    "transcript": str(transcript) if transcript else None,
                    "cull_retakes": request.cull_retakes,
                },
            )
        except VideoFlowError as exc:
            raise HTTPException(status_code=status_for(exc.code), detail=exc.to_dict()) from exc
        return {"ok": True, "job": job.to_dict()}

    @app.get("/api/v1/jobs")
    def list_jobs() -> dict[str, object]:
        return {"ok": True, "jobs": [job.to_dict() for job in jobs.list()]}

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, object]:
        try:
            return {"ok": True, "job": jobs.get(job_id).to_dict()}
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc

    @app.post("/api/v1/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict[str, object]:
        try:
            return {"ok": True, "job": jobs.cancel(job_id).to_dict()}
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc

    @app.get("/api/v1/jobs/{job_id}/events")
    def job_events(job_id: str) -> StreamingResponse:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc

        def stream() -> Iterator[str]:
            last: tuple[object, ...] | None = None
            while True:
                payload = job.to_dict()
                marker = (payload["status"], payload["progress"], payload["stage"])
                if marker != last:
                    last = marker
                    yield f"data: {json.dumps(payload)}\n\n"
                if str(payload["status"]) in TERMINAL:
                    break
                time.sleep(0.2)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/api/v1/jobs/{job_id}/state")
    def job_state(job_id: str) -> dict[str, object]:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        path = (job.output / "project_state.json").expanduser().resolve()
        output = job.output.expanduser().resolve()
        if not path.is_relative_to(output) or not path.is_file():
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "state_not_found",
                    "message": "The job has not written a project state yet.",
                },
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=500,
                detail={"ok": False, "code": "state_invalid", "message": str(exc)},
            ) from exc
        return payload if isinstance(payload, dict) else {"state": payload}

    @app.get("/api/v1/jobs/{job_id}/artifacts/{target}")
    def download_artifact(job_id: str, target: str) -> FileResponse:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        artifacts = (job.result or {}).get("artifacts") or {}
        raw = artifacts.get(target) if isinstance(artifacts, dict) else None
        if not raw:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "artifact_not_found", "message": target},
            )
        path = Path(str(raw)).expanduser().resolve()
        output = job.output.expanduser().resolve()
        if not path.is_relative_to(output) or not path.is_file():
            raise HTTPException(
                status_code=403,
                detail={
                    "ok": False,
                    "code": "artifact_not_allowed",
                    "message": "Artifact is outside the job output.",
                },
            )
        return FileResponse(path, filename=path.name)

    @app.get("/api/v1/system")
    def system() -> dict[str, object]:
        return {
            "ok": True,
            "version": __version__,
            "home": str(portable_home()),
            "allowed_roots": [str(item) for item in allowed_roots()],
            "ffmpeg": find_binary("ffmpeg"),
            "ffprobe": find_binary("ffprobe"),
        }


def status_for(code: str) -> int:
    return {
        "path_not_allowed": 403,
        "job_queue_full": 429,
        "job_not_found": 404,
        "invalid_time": 422,
    }.get(code, 400)
