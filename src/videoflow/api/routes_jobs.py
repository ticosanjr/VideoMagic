"""Job lifecycle, query, event, and log routes."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, model_validator

from videoflow.api.errors import status_for
from videoflow.application.brand_templates import apply_brand_options
from videoflow.application.jobs import TERMINAL, Job, JobManager
from videoflow.application.project_templates import get_template as get_project_template
from videoflow.domain.config import MediaLanguage
from videoflow.domain.errors import StateNotReadyError, VideoFlowError
from videoflow.domain.paths import resolve_allowed
from videoflow.runtime import allowed_roots


class OverrideRequest(BaseModel):
    sentence_id: int = Field(ge=0)
    action: Literal["keep", "discard"]


class VariantSelectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class PriorityRequest(BaseModel):
    priority: int = Field(ge=-100, le=100)


class NewJobRequest(BaseModel):
    source: str = Field(min_length=1)
    output: str = Field(min_length=1)
    idempotency_key: str | None = None
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
    fade_in_ms: int = Field(default=20, ge=0, le=1000)
    fade_out_ms: int = Field(default=20, ge=0, le=1000)
    fade_curve: Literal["linear", "logarithmic"] = "logarithmic"
    handle_check: bool = True
    zooms: bool = True
    zoom_mode: Literal["alternate_cuts", "manual_rules"] = "alternate_cuts"
    zoom_min_scale: float = Field(default=1.0, ge=1.0, le=4.0)
    zoom_max_scale: float = Field(default=1.5, ge=1.0, le=4.0)
    punch_in_scale: float = Field(default=1.15, ge=1.0, le=4.0)
    anchor_point: Literal["center", "upper_third", "face_detect"] = "upper_third"
    progressive_zoom: bool = False
    pan_direction: Literal["none", "left_to_right", "right_to_left"] = "none"
    dialect: Literal["1.9", "1.10"] = "1.9"
    export_targets: list[Literal["resolve", "premiere", "kdenlive", "mp4"]] = Field(
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
    shorts_min_count: int | None = Field(default=None, ge=1, le=20)
    shorts_min_sec: int = Field(default=30, ge=1, le=300)
    shorts_max_sec: int = Field(default=60, ge=1, le=600)
    shorts_subtitles: bool = True
    shorts_selection_mode: Literal["auto", "llm", "heuristic"] = "auto"
    shorts_prompt: str = Field(default="", max_length=2000)
    shorts_reprompt: str = Field(default="", max_length=2000)
    shorts_prompt_mode: Literal["replace", "refine"] = "replace"
    shorts_hook_mode: Literal["off", "metadata", "repeat", "reorder"] = "off"
    shorts_remove_fillers: bool = False
    shorts_filler_words: list[str] = Field(
        default_factory=lambda: ["hum", "hmm", "uh", "um", "ah", "eh", "erm", "er"]
    )
    shorts_audio_energy_boost: bool = False
    shorts_scene_change_boost: bool = False
    shorts_reframe_mode: Literal[
        "center_crop_9_16", "motion_tracking", "face_tracking", "auto_face_tracking_yolo"
    ] = "center_crop_9_16"
    shorts_aspect: Literal["9:16", "1:1", "16:9"] = "9:16"
    shorts_resolution: Literal[1080, 1440, 2160] = 1080
    shorts_source_start_sec: float = Field(default=0.0, ge=0.0)
    shorts_source_end_sec: float | None = Field(default=None, ge=0.0)
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)
    audio_enhance: bool = False
    audio_highpass_hz: int = Field(default=80, ge=20, le=500)
    audio_denoise: bool = True
    audio_denoise_db: int = Field(default=12, ge=1, le=30)
    audio_noise_floor_db: int = Field(default=-30, ge=-80, le=-5)
    audio_loudnorm: bool = True
    audio_target_lufs: float = Field(default=-16.0, ge=-30.0, le=-8.0)
    audio_true_peak_db: float = Field(default=-1.5, ge=-9.0, le=0.0)
    overlay_enabled: bool = False
    overlay_asset: str = ""
    overlay_position: Literal[
        "top_left", "top_right", "bottom_left", "bottom_right", "center"
    ] = "bottom_right"
    overlay_margin_px: int = Field(default=32, ge=0, le=400)
    overlay_width_ratio: float = Field(default=0.18, ge=0.03, le=1.0)
    overlay_opacity: float = Field(default=0.9, ge=0.0, le=1.0)
    music_enabled: bool = False
    music_asset: str = ""
    music_volume: float = Field(default=0.18, ge=0.0, le=1.0)
    music_ducking: bool = True
    music_fade_in_ms: int = Field(default=250, ge=0, le=5000)
    music_fade_out_ms: int = Field(default=500, ge=0, le=5000)
    intro_enabled: bool = False
    intro_asset: str = ""
    intro_duration_sec: float = Field(default=2.0, ge=0.2, le=10.0)
    outro_enabled: bool = False
    outro_asset: str = ""
    outro_duration_sec: float = Field(default=2.0, ge=0.2, le=10.0)
    caption_font_family: str = "Arial"
    caption_font_size: int = Field(default=72, ge=8, le=300)
    caption_font_weight: Literal["normal", "bold"] = "bold"
    caption_italic: bool = False
    caption_uppercase: bool = False
    caption_primary_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    caption_highlight_color: str = Field(default="#FFD400", pattern=r"^#[0-9A-Fa-f]{6}$")
    caption_outline_color: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    caption_outline_width: int = Field(default=4, ge=0, le=20)
    caption_shadow_color: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    caption_shadow_offset: int = Field(default=2, ge=0, le=20)
    caption_shadow_opacity: float = Field(default=0.6, ge=0.0, le=1.0)
    caption_background_color: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    caption_background_opacity: float = Field(default=0.0, ge=0.0, le=1.0)
    caption_background_padding: int = Field(default=0, ge=0, le=40)
    caption_alignment: int = Field(default=2, ge=1, le=9)
    caption_position_x: float = Field(default=0.5, ge=0.0, le=1.0)
    caption_position_y: float = Field(default=0.78, ge=0.0, le=1.0)
    caption_max_width: float = Field(default=0.9, ge=0.2, le=1.0)
    caption_animation: Literal["none", "pop", "sweep"] = "none"
    caption_word_timing: Literal["engine", "proportional", "sentence"] = "engine"
    caption_censor_enabled: bool = False
    caption_censor_words: list[str] = Field(
        default_factory=lambda: [
            "porra", "merda", "caralho", "foda", "fuck", "shit", "bitch", "asshole"
        ]
    )
    caption_censor_replacement: str = Field(default="***", min_length=1, max_length=20)
    caption_keyword_highlight_enabled: bool = False
    caption_keyword_color: str = Field(default="#00E5FF", pattern=r"^#[0-9A-Fa-f]{6}$")
    caption_keyword_words: list[str] = Field(default_factory=list)
    caption_emoji_enabled: bool = False
    caption_emoji_map: dict[str, str] = Field(default_factory=dict)
    caption_brand_vocabulary: dict[str, str] = Field(default_factory=dict)
    overrides: list[OverrideRequest] = Field(default_factory=list)
    transcribe: bool = False
    asr_base_url: str | None = None
    asr_model: str = "whisper-1"
    asr_language: MediaLanguage = "pt"
    whisper_engine: Literal["auto", "faster-whisper", "whisper.cpp"] = "auto"
    whisper_model_size: Literal["tiny", "base", "small", "medium", "large-v3"] = "small"
    whisper_device: Literal["cpu", "cuda"] = "cpu"
    whisper_compute_type: Literal["int8", "float16", "float32"] = "int8"
    whisper_vad_filter: bool = False
    whisper_model: str | None = None
    faster_whisper_model: str | None = None
    brand_template: str | None = None
    project_template: str | None = None


    @model_validator(mode="after")
    def validate_windows(self) -> NewJobRequest:
        if self.zoom_min_scale > self.zoom_max_scale:
            raise ValueError("zoom_min_scale exceeds zoom_max_scale")
        if not self.zoom_min_scale <= self.punch_in_scale <= self.zoom_max_scale:
            raise ValueError("punch_in_scale must be inside the zoom window")
        if self.shorts_min_count is not None and self.shorts_min_count > self.shorts_count:
            raise ValueError("shorts_min_count exceeds shorts_count")
        if (
            self.shorts_source_end_sec is not None
            and self.shorts_source_end_sec <= self.shorts_source_start_sec
        ):
            raise ValueError("shorts_source_end_sec must be greater than shorts_source_start_sec")
        return self


class ResumeRequest(BaseModel):
    approved: bool = True
    comment: str = Field(default="", max_length=4000)


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


def register_job_routes(app: FastAPI, jobs: JobManager) -> None:
    """Register the job lifecycle, query, event, and log routes."""

    @app.post("/api/v1/jobs", status_code=202)
    def create_job(request: NewJobRequest) -> dict[str, object]:
        roots = allowed_roots()
        try:
            source = resolve_allowed(Path(request.source), roots)
            output = resolve_allowed(Path(request.output), roots)
            transcript = (
                resolve_allowed(Path(request.transcript), roots) if request.transcript else None
            )
            options = {
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
                    "fade_in_ms": request.fade_in_ms,
                    "fade_out_ms": request.fade_out_ms,
                    "fade_curve": request.fade_curve,
                    "handle_check": request.handle_check,
                    "zooms": request.zooms,
                    "zoom_mode": request.zoom_mode,
                    "zoom_min_scale": request.zoom_min_scale,
                    "zoom_max_scale": request.zoom_max_scale,
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
                    "shorts_min_count": request.shorts_min_count,
                    "shorts_min_sec": request.shorts_min_sec,
                    "shorts_max_sec": request.shorts_max_sec,
                    "shorts_subtitles": request.shorts_subtitles,
                    "shorts_selection_mode": request.shorts_selection_mode,
                    "shorts_prompt": request.shorts_prompt,
                    "shorts_reprompt": request.shorts_reprompt,
                    "shorts_prompt_mode": request.shorts_prompt_mode,
                    "shorts_hook_mode": request.shorts_hook_mode,
                    "shorts_remove_fillers": request.shorts_remove_fillers,
                    "shorts_filler_words": request.shorts_filler_words,
                    "shorts_audio_energy_boost": request.shorts_audio_energy_boost,
                    "shorts_scene_change_boost": request.shorts_scene_change_boost,
                    "shorts_reframe_mode": request.shorts_reframe_mode,
                    "shorts_aspect": request.shorts_aspect,
                    "shorts_resolution": request.shorts_resolution,
                    "shorts_source_start_sec": request.shorts_source_start_sec,
                    "shorts_source_end_sec": request.shorts_source_end_sec,
                    "allow_external_services": request.allow_external_services,
                    "allowed_external_hosts": request.allowed_external_hosts,
                    "audio_enhance": request.audio_enhance,
                    "audio_highpass_hz": request.audio_highpass_hz,
                    "audio_denoise": request.audio_denoise,
                    "audio_denoise_db": request.audio_denoise_db,
                    "audio_noise_floor_db": request.audio_noise_floor_db,
                    "audio_loudnorm": request.audio_loudnorm,
                    "audio_target_lufs": request.audio_target_lufs,
                    "audio_true_peak_db": request.audio_true_peak_db,
                    "overlay_enabled": request.overlay_enabled,
                    "overlay_asset": request.overlay_asset,
                    "overlay_position": request.overlay_position,
                    "overlay_margin_px": request.overlay_margin_px,
                    "overlay_width_ratio": request.overlay_width_ratio,
                    "overlay_opacity": request.overlay_opacity,
                    "music_enabled": request.music_enabled,
                    "music_asset": request.music_asset,
                    "music_volume": request.music_volume,
                    "music_ducking": request.music_ducking,
                    "music_fade_in_ms": request.music_fade_in_ms,
                    "music_fade_out_ms": request.music_fade_out_ms,
                    "intro_enabled": request.intro_enabled,
                    "intro_asset": request.intro_asset,
                    "intro_duration_sec": request.intro_duration_sec,
                    "outro_enabled": request.outro_enabled,
                    "outro_asset": request.outro_asset,
                    "outro_duration_sec": request.outro_duration_sec,
                    "caption_font_family": request.caption_font_family,
                    "caption_font_size": request.caption_font_size,
                    "caption_font_weight": request.caption_font_weight,
                    "caption_italic": request.caption_italic,
                    "caption_uppercase": request.caption_uppercase,
                    "caption_primary_color": request.caption_primary_color,
                    "caption_highlight_color": request.caption_highlight_color,
                    "caption_outline_color": request.caption_outline_color,
                    "caption_outline_width": request.caption_outline_width,
                    "caption_shadow_color": request.caption_shadow_color,
                    "caption_shadow_offset": request.caption_shadow_offset,
                    "caption_shadow_opacity": request.caption_shadow_opacity,
                    "caption_background_color": request.caption_background_color,
                    "caption_background_opacity": request.caption_background_opacity,
                    "caption_background_padding": request.caption_background_padding,
                    "caption_alignment": request.caption_alignment,
                    "caption_position_x": request.caption_position_x,
                    "caption_position_y": request.caption_position_y,
                    "caption_max_width": request.caption_max_width,
                    "caption_animation": request.caption_animation,
                    "caption_word_timing": request.caption_word_timing,
                    "caption_censor_enabled": request.caption_censor_enabled,
                    "caption_censor_words": request.caption_censor_words,
                    "caption_censor_replacement": request.caption_censor_replacement,
                    "caption_keyword_highlight_enabled": request.caption_keyword_highlight_enabled,
                    "caption_keyword_color": request.caption_keyword_color,
                    "caption_keyword_words": request.caption_keyword_words,
                    "caption_emoji_enabled": request.caption_emoji_enabled,
                    "caption_emoji_map": request.caption_emoji_map,
                    "caption_brand_vocabulary": request.caption_brand_vocabulary,
                    "overrides": [item.model_dump() for item in request.overrides],
                    "transcribe": request.transcribe,
                    "asr_base_url": request.asr_base_url,
                    "asr_model": request.asr_model,
                    "asr_language": request.asr_language,
                    "whisper_engine": request.whisper_engine,
                    "whisper_model_size": request.whisper_model_size,
                    "whisper_device": request.whisper_device,
                    "whisper_compute_type": request.whisper_compute_type,
                    "whisper_vad_filter": request.whisper_vad_filter,
                    "whisper_model": request.whisper_model,
                    "faster_whisper_model": request.faster_whisper_model,
                }
            if request.project_template:
                options.update(get_project_template(request.project_template).options)
            if request.brand_template:
                options = apply_brand_options(options, request.brand_template)
            job = jobs.start(
                source,
                output,
                options=options,
                queue=True,
                idempotency_key=request.idempotency_key,
            )
        except VideoFlowError as exc:
            raise HTTPException(status_code=status_for(exc.code), detail=exc.to_dict()) from exc
        return {"ok": True, "job": job.to_dict()}

    @app.get("/api/v1/jobs")
    def list_jobs(
        limit: int | None = None, offset: int = 0, summary: bool = False
    ) -> dict[str, object]:
        all_jobs = jobs.list()
        start = max(0, int(offset))
        selected = (
            all_jobs[start:]
            if limit is None
            else all_jobs[start : start + max(0, int(limit))]
        )
        return {
            "ok": True,
            "jobs": [job.to_dict(summary=summary) for job in selected],
            "total": len(all_jobs),
        }

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, object]:
        try:
            return {"ok": True, "job": jobs.get(job_id).to_dict()}
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc

    @app.post("/api/v1/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, force: bool = False) -> dict[str, object]:
        try:
            return {
                "ok": True,
                "job": jobs.cancel(job_id, force=force).to_dict(),
            }
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc

    @app.post("/api/v1/jobs/cancel_all")
    def cancel_all_jobs(force: bool = True) -> dict[str, object]:
        return {
            "ok": True,
            "jobs": [job.to_dict() for job in jobs.cancel_all(force=force)],
        }

    @app.delete("/api/v1/jobs/{job_id}")
    def remove_job(job_id: str, force: bool = False) -> dict[str, object]:
        try:
            jobs.remove(job_id, force=force)
            return {"ok": True, "removed": job_id}
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc

    @app.post("/api/v1/jobs/{job_id}/pause")
    def pause_job(job_id: str) -> dict[str, object]:
        return {"ok": True, "job": jobs.pause(job_id).to_dict()}

    @app.post("/api/v1/jobs/{job_id}/unpause")
    def unpause_job(job_id: str) -> dict[str, object]:
        return {"ok": True, "job": jobs.unpause(job_id).to_dict()}

    @app.patch("/api/v1/jobs/{job_id}/priority")
    def set_job_priority(job_id: str, request: PriorityRequest) -> dict[str, object]:
        return {"ok": True, "job": jobs.set_priority(job_id, request.priority).to_dict()}

    @app.post("/api/v1/jobs/{job_id}/retry", status_code=202)
    def retry_job(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status not in {"failed", "cancelled"}:
            raise StateNotReadyError("Only failed or cancelled jobs can be retried.")
        retried = jobs.start(
            job.source,
            job.output,
            {**job.options, "resume": True},
            queue=True,
        )
        return {"ok": True, "job": retried.to_dict()}

    @app.post("/api/v1/jobs/{job_id}/resume", status_code=202)
    def resume_job(job_id: str, request: ResumeRequest) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "waiting_approval":
            raise StateNotReadyError("The job is not waiting for approval.")
        gate = str((job.error or {}).get("gate_id") or "review")
        approvals = job.output / "approvals"
        approvals.mkdir(parents=True, exist_ok=True)
        (approvals / f"{gate}.json").write_text(
            json.dumps(
                {
                    "approved": request.approved,
                    "comment": request.comment,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        resumed = jobs.start(
            job.source,
            job.output,
            {**job.options, "resume": True},
            queue=True,
        )
        return {"ok": True, "job": resumed.to_dict(), "gate": gate}

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

    @app.get("/api/v1/jobs/{job_id}/variants")
    def job_variants(job_id: str) -> dict[str, object]:
        from videoflow.application.variants import compare_variants

        job = jobs.get(job_id)
        return compare_variants(job.output, job.result)

    @app.post("/api/v1/jobs/{job_id}/variants/select")
    def job_variant_winner(
        job_id: str, request: VariantSelectRequest
    ) -> dict[str, object]:
        from videoflow.application.variants import select_variant

        job = jobs.get(job_id)
        payload = select_variant(job.output, request.name)
        return {"ok": True, "winner": payload["selected"]}

    @app.get("/api/v1/jobs/{job_id}/dag")
    def job_dag(job_id: str) -> dict[str, object]:
        from videoflow.application.run_dag import build_run_dag

        job = jobs.get(job_id)
        return build_run_dag(job, jobs.list(limit=60))

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
