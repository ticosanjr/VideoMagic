"""Project and job routes for the local API."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from videoflow import __version__
from videoflow.application.jobs import TERMINAL, JobManager
from videoflow.domain.errors import VideoFlowError
from videoflow.domain.paths import resolve_allowed
from videoflow.runtime import allowed_roots, find_binary, portable_home


class OverrideRequest(BaseModel):
    sentence_id: int = Field(ge=0)
    action: Literal["keep", "discard"]


class NewJobRequest(BaseModel):
    source: str = Field(min_length=1)
    output: str = Field(min_length=1)
    noise_db: float = Field(default=-30.0, ge=-80.0, le=-5.0)
    min_silence_ms: int = Field(default=400, ge=0, le=10000)
    min_speech_ms: int = Field(default=100, ge=0, le=2000)
    jcut: bool = True
    lcut: bool = False
    offset_ms: int = Field(default=200, ge=100, le=500)
    crossfade_ms: int = Field(default=20, ge=10, le=50)
    handle_check: bool = True
    zooms: bool = True
    zoom_mode: Literal["alternate_cuts", "manual_rules"] = "alternate_cuts"
    punch_in_scale: float = Field(default=1.15, ge=1.05, le=1.30)
    anchor_point: Literal["center", "upper_third", "face_detect"] = "upper_third"
    progressive_zoom: bool = False
    pan_direction: Literal["none", "left_to_right", "right_to_left"] = "none"
    dialect: Literal["1.9", "1.10"] = "1.9"
    export_targets: list[Literal["resolve", "premiere", "kdenlive"]] = Field(
        default_factory=lambda: ["resolve", "premiere", "kdenlive"],
        min_length=1,
    )
    transcript: str | None = None
    cull_retakes: bool = False
    strictness: Literal["conservative", "balanced", "aggressive"] = "balanced"
    retake_strategy: Literal["keep_last", "keep_best"] = "keep_last"
    context_window: int = Field(default=15, ge=1, le=100)
    llm_base_url: str | None = None
    llm_model: str = "qwen2.5:7b-instruct"
    shorts: bool = False
    shorts_count: int = Field(default=3, ge=1, le=20)
    shorts_min_sec: int = Field(default=30, ge=1, le=300)
    shorts_max_sec: int = Field(default=60, ge=1, le=600)
    shorts_subtitles: bool = True
    overrides: list[OverrideRequest] = Field(default_factory=list)
    transcribe: bool = False
    asr_base_url: str | None = None
    asr_model: str = "whisper-1"
    asr_language: Literal["pt", "it", "en", "es", "auto"] = "pt"


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
                    "min_speech_ms": request.min_speech_ms,
                    "jcut": request.jcut,
                    "lcut": request.lcut,
                    "offset_ms": request.offset_ms,
                    "crossfade_ms": request.crossfade_ms,
                    "handle_check": request.handle_check,
                    "zooms": request.zooms,
                    "zoom_mode": request.zoom_mode,
                    "punch_in_scale": request.punch_in_scale,
                    "anchor_point": request.anchor_point,
                    "progressive_zoom": request.progressive_zoom,
                    "pan_direction": request.pan_direction,
                    "dialect": request.dialect,
                    "export_targets": request.export_targets,
                    "transcript": str(transcript) if transcript else None,
                    "cull_retakes": request.cull_retakes,
                    "strictness": request.strictness,
                    "retake_strategy": request.retake_strategy,
                    "context_window": request.context_window,
                    "llm_base_url": request.llm_base_url,
                    "llm_model": request.llm_model,
                    "shorts": request.shorts,
                    "shorts_count": request.shorts_count,
                    "shorts_min_sec": request.shorts_min_sec,
                    "shorts_max_sec": request.shorts_max_sec,
                    "shorts_subtitles": request.shorts_subtitles,
                    "overrides": [item.model_dump() for item in request.overrides],
                    "transcribe": request.transcribe,
                    "asr_base_url": request.asr_base_url,
                    "asr_model": request.asr_model,
                    "asr_language": request.asr_language,
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

    @app.get("/api/v1/jobs/{job_id}/logs")
    def job_logs(
        job_id: str,
        module: str | None = None,
        level: str | None = None,
        limit: int = 500,
        download: bool = False,
    ) -> object:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        rows = job.telemetry.logs(
            module=module,
            level=level,
            limit=max(1, min(1000, limit)),
        )
        if download:
            body = "\n".join(
                f"{row['timestamp']} {row['level'].upper():7} {row['module']}: {row['message']}"
                for row in rows
            )
            suffix = f"-{module}" if module else ""
            return PlainTextResponse(
                body + ("\n" if body else ""),
                headers={
                    "Content-Disposition": f'attachment; filename="videoflow-{job_id}{suffix}.log"'
                },
            )
        return {
            "ok": True,
            "logs": rows,
            "count": len(rows),
            "total": job.telemetry.log_count(),
        }

    @app.get("/api/v1/jobs/{job_id}/shorts/{index}")
    def download_short(job_id: str, index: int) -> FileResponse:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        shorts = (job.result or {}).get("shorts") or []
        if not isinstance(shorts, list) or index < 0 or index >= len(shorts):
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "shorts_not_found", "message": str(index)},
            )
        entry = shorts[index]
        raw = entry.get("path") if isinstance(entry, dict) else None
        if not raw:
            raise HTTPException(status_code=404, detail={"ok": False, "code": "shorts_not_found"})
        path = Path(str(raw)).expanduser().resolve()
        output = job.output.expanduser().resolve()
        if not path.is_relative_to(output) or not path.is_file():
            raise HTTPException(
                status_code=403,
                detail={"ok": False, "code": "shorts_not_allowed", "message": "outside output"},
            )
        return FileResponse(path, filename=path.name)

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
