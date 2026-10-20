"""Project and job routes for the local API."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from videoflow import __version__
from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.export_service import export_timeline
from videoflow.application.jobs import TERMINAL, Job, JobManager
from videoflow.application.presets import get_preset, load_presets, save_preset
from videoflow.application.projects import (
    ProjectStore,
    apply_media,
    apply_module_config,
    apply_module_enabled,
    apply_overrides,
    apply_preset,
)
from videoflow.domain.config import ModuleEnabled
from videoflow.domain.errors import (
    CapabilityUnavailableError,
    JobAlreadyRunningError,
    JobNotFoundError,
    MediaNotFoundError,
    MediaNotRegisteredError,
    ModuleBypassedError,
    StateNotReadyError,
    TranscriptNotFoundError,
    TranscriptRequiredError,
    UnknownModuleError,
    VideoFlowError,
)
from videoflow.domain.paths import resolve_allowed
from videoflow.domain.state import ManualOverride, MediaInfo
from videoflow.domain.transcript import format_srt
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
    vad_engine: Literal["auto", "silero", "ffmpeg"] = "auto"
    speech_threshold: float = Field(default=0.5, ge=0.1, le=0.9)
    speech_pad_before_ms: int = Field(default=120, ge=0, le=2000)
    speech_pad_after_ms: int = Field(default=150, ge=0, le=2000)
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
    whisper_model: str | None = None


class NewProjectRequest(BaseModel):
    root: str = Field(min_length=1)
    preset: str | None = None


class MediaRequest(BaseModel):
    file_path: str = Field(min_length=1)


class EnabledRequest(BaseModel):
    enabled: bool


class ProjectRunRequest(BaseModel):
    run_upstream: bool = False
    force: bool = False


class ExportRequest(BaseModel):
    targets: list[Literal["resolve", "premiere", "kdenlive"]] | None = None
    dialect: Literal["1.9", "1.10"] | None = None


class TranscriptOverridesRequest(BaseModel):
    overrides: list[ManualOverride] = Field(default_factory=list)


def _job_event_stream(job: Job) -> Iterator[str]:
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


def register_routes(
    app: FastAPI, jobs: JobManager, projects: ProjectStore
) -> None:
    project_job_lock = threading.Lock()
    app.state.project_store = projects
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
                    "vad_engine": request.vad_engine,
                    "speech_threshold": request.speech_threshold,
                    "speech_pad_before_ms": request.speech_pad_before_ms,
                    "speech_pad_after_ms": request.speech_pad_after_ms,
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
                    "whisper_model": request.whisper_model,
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

        return StreamingResponse(
            _job_event_stream(job),
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

    def fail(exc: VideoFlowError) -> None:
        raise HTTPException(status_code=status_for(exc.code), detail=exc.to_dict()) from exc

    def project_jobs(project_id: UUID) -> list[Job]:
        key = str(project_id)
        return [
            job for job in jobs.list() if str(job.options.get("project_id")) == key
        ]

    def active_project_job(project_id: UUID) -> Job | None:
        for job in project_jobs(project_id):
            if job.status not in TERMINAL:
                return job
        return None

    def assert_project_idle(project_id: UUID) -> None:
        active = active_project_job(project_id)
        if active is not None:
            raise JobAlreadyRunningError(active.stage)

    @app.post("/api/v1/projects", status_code=201)
    def create_project(request: NewProjectRequest) -> dict[str, object]:
        try:
            record, state = projects.create(Path(request.root), preset=request.preset)
        except VideoFlowError as exc:
            fail(exc)
        return {"ok": True, "project": record.to_dict(), "state": state.model_dump(mode="json")}

    @app.get("/api/v1/projects")
    def list_projects() -> dict[str, object]:
        try:
            return {"ok": True, "projects": [record.to_dict() for record in projects.list()]}
        except VideoFlowError as exc:
            fail(exc)

    @app.get("/api/v1/projects/{project_id}/state")
    def project_state(project_id: UUID) -> dict[str, object]:
        try:
            return projects.read_state(project_id).model_dump(mode="json")
        except VideoFlowError as exc:
            fail(exc)

    @app.post("/api/v1/projects/{project_id}/media")
    def register_media(project_id: UUID, request: MediaRequest) -> dict[str, object]:
        try:
            projects.get(project_id)
            source = resolve_allowed(Path(request.file_path), allowed_roots())
            if not source.is_file():
                raise MediaNotFoundError(str(source))
            with project_job_lock:
                assert_project_idle(project_id)
                media = probe_media(source)
                state = apply_media(projects.read_state(project_id), media)
                state, record = projects.save_state(project_id, state)
        except VideoFlowError as exc:
            fail(exc)
        return {
            "ok": True,
            "project": record.to_dict(),
            "media": media.model_dump(mode="json"),
            "state": state.model_dump(mode="json"),
        }

    @app.put("/api/v1/projects/{project_id}/modules/{module_id}/config")
    def update_module_config(
        project_id: UUID, module_id: str, patch: dict[str, Any]
    ) -> dict[str, object]:
        try:
            with project_job_lock:
                assert_project_idle(project_id)
                state = projects.read_state(project_id)
                try:
                    updated = apply_module_config(state, module_id, patch)
                except ValidationError as exc:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "ok": False,
                            "code": "invalid_config",
                            "message": str(exc),
                        },
                    ) from exc
                state, record = projects.save_state(project_id, updated)
        except VideoFlowError as exc:
            fail(exc)
        config = getattr(state.modules_config, module_id).model_dump(mode="json")
        return {
            "ok": True,
            "project": record.to_dict(),
            "module_id": module_id,
            "config": config,
            "state": state.model_dump(mode="json"),
        }

    @app.put("/api/v1/projects/{project_id}/modules/{module_id}/enabled")
    def update_module_enabled(
        project_id: UUID, module_id: str, request: EnabledRequest
    ) -> dict[str, object]:
        try:
            with project_job_lock:
                assert_project_idle(project_id)
                updated = apply_module_enabled(
                    projects.read_state(project_id), module_id, request.enabled
                )
                state, record = projects.save_state(project_id, updated)
        except VideoFlowError as exc:
            fail(exc)
        return {
            "ok": True,
            "project": record.to_dict(),
            "module_id": module_id,
            "enabled": request.enabled,
            "state": state.model_dump(mode="json"),
        }

    @app.post("/api/v1/projects/{project_id}/modules/{module_id}/run")
    def run_module(project_id: UUID, module_id: str) -> dict[str, object]:
        try:
            projects.get(project_id)
            if module_id not in ModuleEnabled.model_fields:
                raise UnknownModuleError(module_id)
            raise CapabilityUnavailableError(
                "module_run",
                "Per-module reruns are not implemented in this build. "
                "Run the full project pipeline instead.",
            )
        except VideoFlowError as exc:
            fail(exc)

    @app.post("/api/v1/projects/{project_id}/run", status_code=202)
    def run_project(project_id: UUID, request: ProjectRunRequest) -> dict[str, object]:
        del request
        try:
            record = projects.get(project_id)
            state = projects.read_state(project_id)
            media = state.media_info
            if media is None:
                raise MediaNotRegisteredError("Register source media before running.")
            source = resolve_allowed(Path(media.source_path), allowed_roots())
            if not source.is_file():
                raise MediaNotFoundError(str(source))
            if not state.module_enabled.ingest:
                raise ModuleBypassedError("ingest")
            if not state.module_enabled.vad:
                raise ModuleBypassedError("vad")
            if state.manual_overrides and not state.transcript:
                raise TranscriptRequiredError(
                    "Manual overrides require a transcript."
                )
            if (
                state.module_enabled.shorts
                and not state.transcript
                and not state.module_enabled.transcribe
            ):
                raise TranscriptRequiredError(
                    "Shorts require a transcript or an enabled transcribe module."
                )
            with project_job_lock:
                assert_project_idle(project_id)
                options = projects.run_options(record, state)
                job = jobs.start(
                    source,
                    record.videoflow_dir,
                    options,
                    finalizer=lambda _job: projects.record_job_state(project_id),
                )
        except VideoFlowError as exc:
            fail(exc)
        return {"ok": True, "job": job.to_dict()}

    @app.post("/api/v1/projects/{project_id}/cancel")
    def cancel_project(project_id: UUID) -> dict[str, object]:
        try:
            projects.get(project_id)
            with project_job_lock:
                active = active_project_job(project_id)
                if active is None:
                    raise JobNotFoundError("The project has no active job.")
                job = jobs.cancel(str(active.job_id))
        except VideoFlowError as exc:
            fail(exc)
        return {"ok": True, "job": job.to_dict()}

    @app.get("/api/v1/projects/{project_id}/events")
    def project_events(project_id: UUID) -> StreamingResponse:
        try:
            projects.get(project_id)
            matching = project_jobs(project_id)
            if not matching:
                raise JobNotFoundError("The project has no jobs yet.")
            job = matching[0]
        except VideoFlowError as exc:
            fail(exc)
        return StreamingResponse(
            _job_event_stream(job),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/api/v1/projects/{project_id}/transcript")
    def project_transcript(
        project_id: UUID, include_word_timestamps: bool = True
    ) -> dict[str, object]:
        try:
            state = projects.read_state(project_id)
        except VideoFlowError as exc:
            fail(exc)
        if not state.transcript:
            fail(TranscriptNotFoundError("The project has no transcript yet."))
        rate = state.media_info.audio_sample_rate if state.media_info else 48000
        transcript: list[dict[str, object]] = []
        for sentence in state.transcript:
            item: dict[str, object] = {
                "id": sentence.id,
                "start_sample": sentence.start_sample,
                "end_sample": sentence.end_sample,
                "text": sentence.text,
            }
            if include_word_timestamps:
                item["words"] = [word.model_dump(mode="json") for word in sentence.words]
            transcript.append(item)
        return {
            "ok": True,
            "project_id": str(state.project_id),
            "revision": state.revision,
            "sample_rate": rate,
            "sentence_count": len(state.transcript),
            "transcript": transcript,
            "srt": format_srt(state.transcript, rate),
        }

    @app.patch("/api/v1/projects/{project_id}/transcript/overrides")
    def update_transcript_overrides(
        project_id: UUID, request: TranscriptOverridesRequest
    ) -> dict[str, object]:
        try:
            with project_job_lock:
                assert_project_idle(project_id)
                state = projects.read_state(project_id)
                if not state.transcript:
                    raise TranscriptNotFoundError("The project has no transcript yet.")
                updated = apply_overrides(state, request.overrides)
                state, record = projects.save_state(project_id, updated)
        except VideoFlowError as exc:
            fail(exc)
        return {
            "ok": True,
            "project": record.to_dict(),
            "state": state.model_dump(mode="json"),
        }

    @app.post("/api/v1/projects/{project_id}/exports")
    def project_exports(project_id: UUID, request: ExportRequest) -> dict[str, object]:
        try:
            with project_job_lock:
                assert_project_idle(project_id)
                record = projects.get(project_id)
                state = projects.read_state(project_id)
                if not state.video_segments:
                    raise StateNotReadyError(
                        "The project has no timeline to export yet."
                    )
                targets = request.targets
                if targets is None:
                    export_config = state.modules_config.export
                    targets = []
                    if export_config.write_fcpxml:
                        targets.append("resolve")
                    if export_config.write_xmeml:
                        targets.append("premiere")
                    if export_config.write_otio:
                        targets.append("kdenlive")
                if not targets:
                    raise StateNotReadyError("No export targets are enabled.")
                dialect = request.dialect or state.modules_config.export.fcpxml_dialect
                artifacts = export_timeline(
                    state,
                    record.videoflow_dir / "exports",
                    targets=targets,
                    dialect=dialect,
                )
        except VideoFlowError as exc:
            fail(exc)
        return {
            "ok": True,
            "project": record.to_dict(),
            "state_revision": state.revision,
            "artifacts": {name: str(path) for name, path in artifacts.items()},
        }

    @app.post("/api/v1/projects/{project_id}/presets/{name}/apply")
    def apply_project_preset(project_id: UUID, name: str) -> dict[str, object]:
        try:
            entry = get_preset(name)
            with project_job_lock:
                assert_project_idle(project_id)
                state = apply_preset(projects.read_state(project_id), entry.preset)
                state, record = projects.save_state(project_id, state)
        except VideoFlowError as exc:
            fail(exc)
        return {
            "ok": True,
            "project": record.to_dict(),
            "preset": entry.to_dict(),
            "state": state.model_dump(mode="json"),
        }

    @app.get("/api/v1/presets")
    def list_presets() -> dict[str, object]:
        try:
            return {"ok": True, "presets": [entry.to_dict() for entry in load_presets()]}
        except VideoFlowError as exc:
            fail(exc)

    @app.get("/api/v1/presets/{name}")
    def read_preset(name: str) -> dict[str, object]:
        try:
            return {"ok": True, "preset": get_preset(name).to_dict()}
        except VideoFlowError as exc:
            fail(exc)

    @app.put("/api/v1/presets/{name}")
    def write_preset(name: str, payload: dict[str, Any]) -> dict[str, object]:
        try:
            return {"ok": True, "preset": save_preset(name, payload).to_dict()}
        except VideoFlowError as exc:
            fail(exc)

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


def probe_media(path: Path) -> MediaInfo:
    return FFmpegAdapter().probe(path)


def status_for(code: str) -> int:
    return {
        "path_not_allowed": 403,
        "job_queue_full": 429,
        "job_not_found": 404,
        "job_already_running": 409,
        "project_not_found": 404,
        "project_exists": 409,
        "project_state_invalid": 500,
        "preset_not_found": 404,
        "preset_invalid": 422,
        "invalid_preset_name": 422,
        "unknown_module": 404,
        "module_bypassed": 409,
        "media_not_found": 422,
        "media_not_registered": 409,
        "state_not_ready": 409,
        "transcript_not_found": 404,
        "transcript_required": 422,
        "invalid_override": 422,
        "word_overrides_not_supported": 422,
        "invalid_time": 422,
        "invalid_config": 422,
        "export_failed": 422,
        "ingest_failed": 422,
        "not_implemented": 501,
    }.get(code, 400)
