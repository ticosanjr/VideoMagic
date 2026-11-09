"""Project and job routes for the local API."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.api.errors import status_for
from videoflow.api.routes_admin import register_admin_routes
from videoflow.api.routes_assets import register_asset_routes
from videoflow.api.routes_discovery import register_discovery_routes
from videoflow.api.routes_hilt import register_hilt_routes
from videoflow.api.routes_jobs import register_job_routes
from videoflow.api.routes_library import register_library_routes
from videoflow.api.routes_presets import register_preset_routes
from videoflow.api.routes_providers import register_provider_routes
from videoflow.api.routes_publish import register_publish_routes
from videoflow.api.routes_recipes import (
    RecipeRunRequest,
    register_recipe_routes,
    start_recipe_job,
)
from videoflow.api.routes_schedules import register_schedule_routes
from videoflow.api.routes_system import register_system_routes
from videoflow.api.routes_timeline import (
    _apply_and_store,
    _assert_tracks_unlocked,
    _timeline_etag,
    _timeline_history,
    _timeline_state_path,
    register_timeline_routes,
)
from videoflow.application.broll_approval import (
    load_approvals,
    redo_approval,
    save_approval,
    undo_approval,
)
from videoflow.application.caption_ai import apply_llm_emoji
from videoflow.application.deliverables import (
    add_review_comment,
    approve_review,
    list_review_comments,
    list_thumbnails,
    record_thumbnail_metric,
    review_payload,
    select_thumbnail,
    thumbnail_metrics,
)
from videoflow.application.dubbing import generate_short_dubbing
from videoflow.application.filesystem import create_directory, list_directory, roots_payload
from videoflow.application.jobs import JobManager
from videoflow.application.live_source import live_sources
from videoflow.application.multimodal import analyze_short_entry
from videoflow.application.multimodal_llm import analyze_short_llm_entry
from videoflow.application.nle_validation import validate_nle_exports
from videoflow.application.previews import (
    build_preview,
    preview_paths,
    previews,
    write_preview_manifest,
)
from videoflow.application.providers import (
    first_provider,
)
from videoflow.application.render_queue import renders
from videoflow.application.secrets import (
    get_secret,
)
from videoflow.application.settings import (
    load_settings,
)
from videoflow.application.short_editor import ShortEditOptions
from videoflow.application.short_editor import edit_short as edit_short_service
from videoflow.application.short_metadata import generate_short_metadata
from videoflow.application.state_cache import load_state
from videoflow.application.step_outputs import (
    load_step_outputs,
    save_step_outputs,
    step_output_port,
    summarize_step_outputs,
)
from videoflow.application.thumbnail import generate_short_thumbnail
from videoflow.application.timeline_edit import TimelineEdit, apply_timeline_edit
from videoflow.application.url_import import import_url
from videoflow.application.voiceover import generate_short_voiceover
from videoflow.core.recipe import parse_recipe
from videoflow.domain.config import (
    DubbingConfig,
    TtsConfig,
)
from videoflow.domain.errors import (
    CapabilityUnavailableError,
    FilesystemError,
    MediaNotFoundError,
    RecipeError,
    StateNotReadyError,
    VideoFlowError,
)
from videoflow.domain.paths import resolve_allowed
from videoflow.domain.state import MediaInfo, ProjectState
from videoflow.engine.batch import BatchManager
from videoflow.engine.recipes import (
    get_recipe,
    list_recipes,
    resolve_recipe_paths,
)
from videoflow.runtime import allowed_roots
from videoflow.steps import requirements_by_type, step_types
from videoflow.steps.ports import validate_recipe_ports

logger = logging.getLogger(__name__)




class CopilotRecipeRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class CopilotTimelineRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    apply: bool = True


class AssistantRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    approve: bool = False


class AssistantApprovalRequest(BaseModel):
    approval_id: str = Field(min_length=1, max_length=120)


















class BatchRequest(BaseModel):
    source_dir: str = Field(min_length=1)
    output_root: str = Field(min_length=1)
    recipe: dict[str, Any] | None = None
    recipe_id: str | None = None
    recursive: bool = False
    extensions: list[str] = Field(default_factory=list)
    resume: bool = True
    max_files: int = Field(default=200, ge=1, le=2000)

    @model_validator(mode="after")
    def exactly_one_recipe(self) -> BatchRequest:
        if (self.recipe is None) == (self.recipe_id is None):
            raise ValueError("provide exactly one of recipe or recipe_id")
        return self


class MediaImportRequest(BaseModel):
    url: str = Field(min_length=1)
    max_height: int = Field(default=1080, ge=144, le=4320)
    allow_playlist: bool = False
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)


class NewDirectoryRequest(BaseModel):
    parent: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=255)












class ShortDubbingRequest(BaseModel):
    text: str | None = None
    target_language: str = Field(default="en", min_length=2, max_length=20)
    base_url: str | None = None
    model: str = "tts-1"
    voice: str = "alloy"
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    volume: float = Field(default=1.0, ge=0.0, le=1.0)
    original_volume: float = Field(default=0.0, ge=0.0, le=1.0)
    llm_base_url: str | None = None
    llm_model: str = "qwen2.5:7b-instruct"
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)






















class StepOutputSaveRequest(BaseModel):
    target_dir: str = Field(min_length=1)






class ReviewDecisionRequest(BaseModel):
    approved: bool
    comment: str = Field(default="", max_length=4000)
    reviewer: str = Field(default="", max_length=120)


class ThumbnailSelectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)


class ThumbnailMetricRequest(BaseModel):
    impressions: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)


class ReviewCommentRequest(BaseModel):
    author: str = Field(default="local operator", max_length=120)
    text: str = Field(min_length=1, max_length=4000)
    time_sec: float | None = Field(default=None, ge=0.0)


class BrollApprovalRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    approved: list[int] = Field(default_factory=list)
    order: list[int] = Field(default_factory=list)










class ShortVoiceoverRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    provider: Literal["openai_compatible", "piper"] = "openai_compatible"
    base_url: str | None = None
    model: str = "tts-1"
    voice: str = "alloy"
    binary: str = "piper"
    model_path: str = ""
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    volume: float = Field(default=1.0, ge=0.0, le=1.0)
    original_volume: float = Field(default=0.35, ge=0.0, le=1.0)
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)


class ShortThumbnailRequest(BaseModel):
    time_sec: float | None = Field(default=None, ge=0.0)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    caption_style: dict[str, Any] | None = None


class ShortVisionRequest(BaseModel):
    base_url: str | None = None
    model: str = "gpt-4o-mini"
    max_frames: int = Field(default=6, ge=1, le=12)
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)






class ShortEmojiRequest(BaseModel):
    base_url: str | None = None
    model: str = "qwen2.5:7b-instruct"
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)


class ShortMetadataRequest(BaseModel):
    platform: Literal["youtube", "tiktok", "instagram", "linkedin"] = "youtube"
    tone: Literal["engaging", "professional", "educational", "bold"] = "engaging"
    extra_hashtags: list[str] = Field(default_factory=list)


class ShortEditRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    start_sec: float | None = Field(default=None, ge=0.0)
    end_sec: float | None = Field(default=None, ge=0.0)
    aspect_ratio: Literal["9:16", "1:1", "16:9"] | None = None
    burn_subtitles: bool | None = None
    caption_style: dict[str, Any] | None = None

    @model_validator(mode="after")
    def ordered_trim(self) -> ShortEditRequest:
        if (
            self.end_sec is not None
            and self.start_sec is not None
            and self.end_sec <= self.start_sec
        ):
            raise ValueError("end_sec must be greater than start_sec")
        return self




def register_routes(
    app: FastAPI,
    jobs: JobManager,
    batches: BatchManager | None = None,
) -> None:
    batch_manager = batches or BatchManager(jobs)
    app.state.batches = batch_manager




    register_asset_routes(app)

    register_discovery_routes(app)

    register_preset_routes(app)













    register_recipe_routes(app, jobs)

    @app.post("/api/v1/batches", status_code=202)
    def create_batch(request: BatchRequest) -> dict[str, object]:
        roots = allowed_roots()
        source_dir = resolve_allowed(Path(request.source_dir), roots)
        output_root = resolve_allowed(Path(request.output_root), roots)
        if request.recipe is not None:
            recipe = parse_recipe(request.recipe)
        else:
            recipe = get_recipe(str(request.recipe_id))
        recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
        validate_recipe_ports(recipe)
        recipe = resolve_recipe_paths(recipe, roots)
        batch = batch_manager.start(
            source_dir,
            output_root,
            recipe.model_dump(mode="json"),
            recipe_id=recipe.id,
            recursive=request.recursive,
            extensions=request.extensions,
            resume=request.resume,
            max_files=request.max_files,
        )
        return {"ok": True, "batch": batch.to_dict()}



    register_system_routes(app)
    register_admin_routes(app)
    register_provider_routes(app)
    register_publish_routes(app, jobs)
    register_library_routes(app)
    register_schedule_routes(app, jobs)


























    @app.get("/api/v1/batches")
    def list_batches(limit: int | None = None, offset: int = 0) -> dict[str, object]:
        batches = batch_manager.list(limit=limit, offset=offset)
        return {
            "ok": True,
            "batches": [batch.to_dict() for batch in batches],
            "total": len(batch_manager.list()),
        }

    @app.post("/api/v1/batches/{batch_id}/resume")
    def resume_batch(batch_id: str) -> dict[str, object]:
        batch = batch_manager.resume(batch_id)
        return {"ok": True, "batch": batch.to_dict()}

    @app.get("/api/v1/batches/{batch_id}")
    def get_batch(batch_id: str) -> dict[str, object]:
        batch = batch_manager.get(batch_id)
        return {"ok": True, "batch": batch.to_dict()}

    @app.post("/api/v1/batches/{batch_id}/cancel")
    def cancel_batch(batch_id: str) -> dict[str, object]:
        batch = batch_manager.cancel(batch_id)
        return {"ok": True, "batch": batch.to_dict()}

    register_job_routes(app, jobs)
    register_hilt_routes(app, jobs)



































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

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/edit")
    def edit_short(
        job_id: str, index: int, request: ShortEditRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded" or job.result is None:
            raise StateNotReadyError(
                "The job must succeed before a Short can be edited."
            )
        entry = edit_short_service(
            source=job.source,
            output=job.output,
            index=index,
            result=job.result,
            options=ShortEditOptions(
                title=request.title,
                start_sec=request.start_sec,
                end_sec=request.end_sec,
                aspect_ratio=request.aspect_ratio,
                burn_subtitles=request.burn_subtitles,
                caption_style=request.caption_style,
            ),
        )
        return {
            "ok": True,
            "short": entry,
            "download": f"/api/v1/jobs/{job_id}/shorts/{index}",
        }

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/captions/emoji")
    def short_emoji(
        job_id: str, index: int, request: ShortEmojiRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded" or job.result is None:
            raise StateNotReadyError(
                "The job must succeed before captions can be edited."
            )
        payload = apply_llm_emoji(
            source=job.source,
            output=job.output,
            index=index,
            result=job.result,
            base_url=request.base_url
            or os.environ.get("VIDEOWFLOW_LLM_BASE_URL")
            or "http://localhost:11434/v1",
            model=request.model,
            api_key=os.environ.get("VIDEOWFLOW_LLM_API_KEY"),
            allow_external_services=request.allow_external_services,
            allowed_external_hosts=tuple(request.allowed_external_hosts),
        )
        return {
            "ok": True,
            "emoji_map": payload["emoji_map"],
            "short": payload["short"],
            "download": f"/api/v1/jobs/{job_id}/shorts/{index}",
        }

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/metadata")
    def short_metadata(
        job_id: str, index: int, request: ShortMetadataRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded" or job.result is None:
            raise StateNotReadyError(
                "The job must succeed before metadata can be generated."
            )
        metadata = generate_short_metadata(
            output=job.output,
            index=index,
            result=job.result,
            platform=request.platform,
            tone=request.tone,
            extra_hashtags=tuple(request.extra_hashtags),
        )
        return {
            "ok": True,
            "metadata": metadata,
            "short": job.result["shorts"][index],
        }

    @app.post("/api/v1/jobs/{job_id}/preview")
    def create_preview(
        job_id: str, force: bool = False, background: bool = False
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded":
            raise StateNotReadyError("The job must succeed before preview rendering.")
        preview = job.output / "preview" / "preview.mp4"
        if background:
            state = previews.start(job)
            return {
                "ok": True,
                "status": state.to_dict(),
                "url": f"/api/v1/jobs/{job_id}/preview/file",
            }
        if not force and previews.is_ready(job):
            return {
                "ok": True,
                "status": "ready",
                "path": str(preview),
                "url": f"/api/v1/jobs/{job_id}/preview/file",
            }
        build_preview(job)
        write_preview_manifest(job)
        return {
            "ok": True,
            "status": "ready",
            "path": str(preview),
            "url": f"/api/v1/jobs/{job_id}/preview/file",
        }

    @app.post("/api/v1/jobs/{job_id}/render", status_code=202)
    def start_render(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded":
            raise StateNotReadyError("The job must succeed before rendering.")
        state = renders.start(job)
        return {"ok": True, "render": state.to_dict()}

    @app.get("/api/v1/jobs/{job_id}/render/status")
    def render_status(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        state = renders.get(job_id)
        ready = renders.is_ready(job)
        if state is None:
            return {
                "ok": True,
                "status": "ready" if ready else "idle",
                "percent": 100 if ready else 0,
            }
        payload = state.to_dict()
        payload["ok"] = True
        payload["ready"] = ready
        if state.status == "ready" and not ready:
            payload["status"] = "failed"
            payload["percent"] = 0
            payload["message"] = "Render is stale"
            payload["error"] = "The timeline changed during rendering. Render again."
            payload["error_details"] = {
                "ok": False,
                "code": "render_stale",
                "message": "The timeline changed during rendering. Render again.",
            }
        return payload

    @app.post("/api/v1/jobs/{job_id}/render/cancel")
    def cancel_render(job_id: str) -> dict[str, object]:
        state = renders.cancel(job_id)
        if state is None:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "render_not_found", "message": job_id},
            )
        return {"ok": True, "render": state.to_dict()}

    @app.get("/api/v1/jobs/{job_id}/render/file")
    def download_render(job_id: str) -> FileResponse:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        path = renders.output_path(job)
        if not renders.is_ready(job):
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "render_not_found", "message": job_id},
            )
        return FileResponse(path, media_type="video/mp4", filename=path.name)

    @app.get("/api/v1/jobs/{job_id}/preview/status")
    def preview_status(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        state = previews.get(job_id)
        ready = previews.is_ready(job)
        if state is None:
            return {
                "ok": True,
                "status": "ready" if ready else "idle",
                "percent": 100 if ready else 0,
            }
        payload = state.to_dict()
        payload["ok"] = True
        payload["ready"] = ready
        if state.status == "ready" and not ready:
            payload["status"] = "stale"
            payload["percent"] = 0
            payload["message"] = "Preview is stale"
        return payload

    @app.post("/api/v1/jobs/{job_id}/preview/cancel")
    def cancel_preview(job_id: str) -> dict[str, object]:
        state = previews.cancel(job_id)
        if state is None:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "preview_not_found", "message": job_id},
            )
        return {"ok": True, "status": state.to_dict()}

    def _frame_target(
        job: Any, revision: int, time_sec: float, height: int
    ) -> Path:
        stamp = int(max(0.0, min(time_sec, 24 * 3600)) * 10)
        height = max(64, min(2160, int(height)))
        return (
            job.output
            / "preview"
            / "frames"
            / str(revision)
            / f"{stamp:08d}-{height}.jpg"
        )

    def _frame_source(
        state: ProjectState, moment: float, preview: Path | None
    ) -> tuple[Path, float]:
        """Map a timeline moment to the matching picture."""

        if preview is not None:
            return preview, moment
        media = state.media_info
        if media is None:
            raise StateNotReadyError("The project has no media info.")
        source = Path(media.source_path).expanduser()
        if not source.is_file():
            raise StateNotReadyError("The source media is not available.")
        fps = media.fps_num / media.fps_den
        frame = int(max(0.0, moment) * fps)
        video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
        if not video:
            return source, moment
        chosen = video[-1]
        for clip in video:
            if clip.timeline_in_frame <= frame < clip.timeline_out_frame:
                chosen = clip
                break
        offset = max(0, frame - chosen.timeline_in_frame)
        source_frame = min(
            chosen.source_out_frame - 1,
            chosen.source_in_frame + offset,
        )
        return source, source_frame / fps

    @app.get("/api/v1/jobs/{job_id}/frames")
    def job_frames(
        job_id: str,
        response: Response,
        start: float = 0.0,
        count: int = 3,
        fps: float = 2.0,
        height: int | None = None,
    ) -> dict[str, object]:
        try:
            job = jobs.get(job_id)
            state_path = _timeline_state_path(job)
            if not state_path.is_file():
                raise StateNotReadyError("The job has no project_state.json timeline.")
            state = load_state(state_path)
            if state.media_info is None:
                raise StateNotReadyError("The project has no media info.")
        except VideoFlowError as exc:
            fail(exc)
            raise
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "frame_invalid", "message": str(exc)},
            ) from exc
        if height is None:
            height = int(load_settings().quality.proxy_height)
        height = max(64, min(2160, int(height)))
        preview = (
            preview_paths(job)[1] if previews.is_ready(job) else None
        )
        count = max(1, min(12, int(count)))
        step = 1.0 / max(1.0, min(30.0, float(fps)))
        frames: list[dict[str, object]] = []
        hits = 0
        revision = state.revision
        for index in range(count):
            moment = max(0.0, start + index * step)
            target = _frame_target(job, revision, moment, height)
            cached = target.is_file()
            if cached:
                hits += 1
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    source, source_time = _frame_source(state, moment, preview)
                    FFmpegAdapter().render_thumbnail(
                        source,
                        target,
                        time_sec=int(source_time * 10) / 10,
                        height=height,
                    )
                except VideoFlowError as exc:
                    fail(exc)
                    raise
                except Exception as exc:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "ok": False,
                            "code": "frame_failed",
                            "message": str(exc),
                        },
                    ) from exc
            frames.append(
                {
                    "time": round(moment, 3),
                    "url": (
                        f"/api/v1/jobs/{job_id}/frame?time={moment:.3f}"
                        f"&height={height}"
                    ),
                    "cached": cached,
                }
            )
        response.headers["X-Frame-Cache"] = f"{hits}/{count}"
        return {
            "ok": True,
            "revision": revision,
            "height": height,
            "frames": frames,
        }

    @app.get("/api/v1/jobs/{job_id}/frame")
    def job_frame(job_id: str, time: float = 0.0, height: int | None = None) -> FileResponse:
        try:
            job = jobs.get(job_id)
            state_path = _timeline_state_path(job)
            if not state_path.is_file():
                raise StateNotReadyError("The job has no project_state.json timeline.")
            state = load_state(state_path)
            if state.media_info is None:
                raise StateNotReadyError("The project has no media info.")
        except VideoFlowError as exc:
            fail(exc)
            raise
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "frame_invalid", "message": str(exc)},
            ) from exc
        if height is None:
            height = int(load_settings().quality.proxy_height)
        height = max(64, min(2160, int(height)))
        preview = (
            preview_paths(job)[1] if previews.is_ready(job) else None
        )
        target = _frame_target(job, state.revision, time, height)
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                moment = int(max(0.0, min(time, 24 * 3600)) * 10) / 10
                source, source_time = _frame_source(state, moment, preview)
                FFmpegAdapter().render_thumbnail(
                    source, target, time_sec=int(source_time * 10) / 10, height=height
                )
            except VideoFlowError as exc:
                fail(exc)
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=422,
                    detail={"ok": False, "code": "frame_failed", "message": str(exc)},
                ) from exc
        return FileResponse(target, media_type="image/jpeg", filename=target.name)

    @app.get("/api/v1/jobs/{job_id}/preview/file")
    def download_preview(job_id: str) -> FileResponse:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        preview = job.output / "preview" / "preview.mp4"
        if not previews.is_ready(job):
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "preview_not_found"},
            )
        return FileResponse(preview, media_type="video/mp4", filename="preview.mp4")













    register_timeline_routes(app, jobs)

    @app.get("/api/v1/jobs/{job_id}/review")
    def job_review(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        return {"ok": True, **review_payload(job.output)}

    @app.patch("/api/v1/jobs/{job_id}/review")
    def decide_job_review(
        job_id: str, request: ReviewDecisionRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        approval = approve_review(
            job.output,
            approved=request.approved,
            comment=request.comment,
            reviewer=request.reviewer,
        )
        return {"ok": True, "approval": approval}

    @app.get("/api/v1/jobs/{job_id}/review/comments")
    def job_review_comments(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        return {"ok": True, "comments": list_review_comments(job.output)}

    @app.post("/api/v1/jobs/{job_id}/review/comments", status_code=201)
    def add_job_review_comment(
        job_id: str, request: ReviewCommentRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        comments = add_review_comment(
            job.output,
            author=request.author,
            text=request.text,
            time_sec=request.time_sec,
        )
        return {"ok": True, "comments": comments}

    @app.get("/api/v1/jobs/{job_id}/thumbnails")
    def job_thumbnails(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        return {"ok": True, **list_thumbnails(job.output)}

    @app.get("/api/v1/jobs/{job_id}/clips/{clip_id}/thumbnail")
    def job_clip_thumbnail(job_id: str, clip_id: str) -> FileResponse:
        job = jobs.get(job_id)
        state_path = Path(
            str((job.result or {}).get("state_path") or job.output / "project_state.json")
        )
        state = ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))
        clip = next(
            (item for item in state.video_segments if item.clip_id == clip_id), None
        )
        if clip is None or state.media_info is None:
            raise StateNotReadyError(f"Unknown clip: {clip_id}")
        media = state.media_info
        fps = media.fps_num / media.fps_den
        slug = "".join(
            char if char.isalnum() or char in "-_" else "-" for char in clip_id
        )
        target = job.output / "thumbnails" / "clips" / f"{slug}.png"
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            midpoint = (clip.source_in_frame + clip.source_out_frame) / 2
            FFmpegAdapter().render_thumbnail(
                Path(media.source_path),
                target,
                time_sec=max(0.0, midpoint / max(1.0, fps)),
            )
        if not target.is_file():
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "clip_thumbnail_not_found"},
            )
        return FileResponse(target, media_type="image/png", filename=target.name)

    @app.get("/api/v1/jobs/{job_id}/thumbnails/metrics")
    def job_thumbnail_metrics(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        return {"ok": True, "metrics": thumbnail_metrics(job.output)}

    @app.get("/api/v1/jobs/{job_id}/thumbnails/{name}")
    def job_thumbnail_file(job_id: str, name: str) -> FileResponse:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        directory = (job.output / "thumbnails").resolve()
        path = (directory / name).resolve()
        if path.parent != directory or not path.is_file():
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "thumbnail_not_found", "message": name},
            )
        return FileResponse(path, media_type="image/png", filename=path.name)

    @app.post("/api/v1/jobs/{job_id}/thumbnails/{name}/metric")
    def record_job_thumbnail_metric(
        job_id: str, name: str, request: ThumbnailMetricRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        metric = record_thumbnail_metric(
            job.output,
            name,
            impressions=request.impressions,
            clicks=request.clicks,
        )
        return {"ok": True, "metric": metric, "metrics": thumbnail_metrics(job.output)}

    @app.post("/api/v1/jobs/{job_id}/thumbnails/select")
    def choose_job_thumbnail(
        job_id: str, request: ThumbnailSelectRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        payload = select_thumbnail(job.output, request.name)
        return {"ok": True, **payload}

    @app.post("/api/v1/jobs/{job_id}/broll/undo")
    def undo_job_broll(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        approval = undo_approval(job.output)
        return {"ok": True, "approval": approval}

    @app.post("/api/v1/jobs/{job_id}/broll/redo")
    def redo_job_broll(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        approval = redo_approval(job.output)
        return {"ok": True, "approval": approval}

    @app.get("/api/v1/jobs/{job_id}/broll")
    def job_broll(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        plan = (job.result or {}).get("broll_plan", {})
        return {
            "ok": True,
            "plan": plan,
            "approval": load_approvals(job.output),
        }

    @app.patch("/api/v1/jobs/{job_id}/broll")
    def update_job_broll(job_id: str, request: BrollApprovalRequest) -> dict[str, object]:
        job = jobs.get(job_id)
        plan = (job.result or {}).get("broll_plan", {})
        approval = save_approval(
            job.output,
            title=request.title,
            approved=request.approved,
            order=request.order,
            plan=plan,
        )
        return {"ok": True, "approval": approval}





















    @app.get("/api/v1/jobs/{job_id}/live-source/status")
    def live_source_status(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        height = 0
        try:
            state = load_state(_timeline_state_path(job))
            if state.media_info is not None:
                height = state.media_info.height
        except (VideoFlowError, OSError, ValueError):
            height = 0
        return {"ok": True, "live_source": live_sources.status(job, height=height).to_dict()}

    @app.post("/api/v1/jobs/{job_id}/live-source")
    def prepare_live_source(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        height = 0
        try:
            state = load_state(_timeline_state_path(job))
            if state.media_info is not None:
                height = state.media_info.height
        except (VideoFlowError, OSError, ValueError):
            height = 0
        return {"ok": True, "live_source": live_sources.start(job, height=height).to_dict()}

    @app.get("/api/v1/jobs/{job_id}/live-source/file")
    def live_source_file(job_id: str) -> FileResponse:
        try:
            job = jobs.get(job_id)
            height = 0
            state = load_state(_timeline_state_path(job))
            if state.media_info is not None:
                height = state.media_info.height
            path = live_sources.file(job, height=height)
            if path is None:
                raise StateNotReadyError("The live source proxy is not ready.")
        except VideoFlowError as exc:
            fail(exc)
            raise
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "live_source_failed", "message": str(exc)},
            ) from exc
        return FileResponse(path, media_type="video/mp4", filename=path.name)

    @app.get("/api/v1/jobs/{job_id}/source/file")
    def job_source_file(job_id: str) -> FileResponse:
        job = jobs.get(job_id)
        state = load_state(_timeline_state_path(job))
        media = state.media_info
        if media is None:
            raise StateNotReadyError("The project has no media info.")
        source = resolve_allowed(Path(media.source_path), allowed_roots())
        if not source.is_file():
            raise StateNotReadyError("The source media is not available.")
        return FileResponse(source, media_type="video/mp4", filename=source.name)


    @app.get("/api/v1/jobs/{job_id}/artifacts/{artifact_name}")
    def download_job_artifact(job_id: str, artifact_name: str) -> FileResponse:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        artifacts = (job.result or {}).get("artifacts") or {}
        raw = artifacts.get(artifact_name) if isinstance(artifacts, dict) else None
        if not raw:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "artifact_not_found", "message": artifact_name},
            )
        path = Path(str(raw)).expanduser().resolve()
        output = job.output.expanduser().resolve()
        if not path.is_relative_to(output) or not path.is_file():
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "artifact_not_found", "message": artifact_name},
            )
        return FileResponse(path, filename=path.name)

    @app.get("/api/v1/jobs/{job_id}/steps/{step_id}/outputs")
    def job_step_outputs(job_id: str, step_id: str) -> dict[str, object]:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        if not step_id or "/" in step_id or "\\" in step_id:
            raise HTTPException(
                status_code=422,
                detail={
                    "ok": False,
                    "code": "step_invalid",
                    "message": "Invalid step id.",
                },
            )
        payload = load_step_outputs(job.output, step_id)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "step_outputs_missing",
                    "message": f"No outputs persisted for step {step_id}.",
                },
            )
        return {"ok": True, **summarize_step_outputs(payload)}

    @app.get("/api/v1/jobs/{job_id}/steps/{step_id}/outputs/{port_id}")
    def job_step_output_port(
        job_id: str, step_id: str, port_id: str
    ) -> dict[str, object]:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        if not step_id or "/" in step_id or "\\" in step_id:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "step_invalid", "message": "Invalid step id."},
            )
        payload = load_step_outputs(job.output, step_id)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "step_outputs_missing",
                    "message": f"No outputs persisted for step {step_id}.",
                },
            )
        item = step_output_port(payload, port_id)
        if item is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "step_port_missing",
                    "message": f"Step {step_id} has no output port {port_id}.",
                },
            )
        return {"ok": True, "step_id": step_id, "port": item}

    @app.get("/api/v1/jobs/{job_id}/steps/{step_id}/files/{file_name}")
    def job_step_output_file(
        job_id: str, step_id: str, file_name: str
    ) -> FileResponse:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        if not step_id or "/" in step_id or "\\" in step_id:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "step_invalid", "message": "Invalid step id."},
            )
        payload = load_step_outputs(job.output, step_id)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "step_outputs_missing",
                    "message": f"No outputs persisted for step {step_id}.",
                },
            )
        for item in payload.get("files", []):
            if not isinstance(item, dict) or str(item.get("name")) != file_name:
                continue
            path = Path(str(item.get("path", ""))).expanduser().resolve()
            if path.is_relative_to(job.output.expanduser().resolve()) and path.is_file():
                return FileResponse(path, filename=path.name)
        raise HTTPException(
            status_code=404,
            detail={
                "ok": False,
                "code": "step_file_missing",
                "message": f"Step {step_id} has no file {file_name}.",
            },
        )

    @app.post("/api/v1/jobs/{job_id}/steps/{step_id}/save")
    def save_job_step_outputs(
        job_id: str, step_id: str, request: StepOutputSaveRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if not step_id or "/" in step_id or "\\" in step_id:
            raise RecipeError("Invalid step id.")
        target = resolve_allowed(Path(request.target_dir), allowed_roots())
        saved = save_step_outputs(job.output, step_id, target)
        if not saved:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "step_outputs_missing",
                    "message": f"No outputs persisted for step {step_id}.",
                },
            )
        return {"ok": True, "saved": saved}

    @app.get("/api/v1/jobs/{job_id}/shorts/{index}/file")
    def download_short_file(job_id: str, index: int) -> FileResponse:
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
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "short_file_not_found"},
            )
        path = Path(str(raw)).expanduser().resolve()
        output = job.output.expanduser().resolve()
        if not path.is_relative_to(output) or not path.is_file():
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "short_file_not_found"},
            )
        return FileResponse(path, media_type="video/mp4", filename=path.name)

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/thumbnail")
    def short_thumbnail(
        job_id: str, index: int, request: ShortThumbnailRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded" or job.result is None:
            raise StateNotReadyError(
                "The job must succeed before a thumbnail can be generated."
            )
        thumbnail = generate_short_thumbnail(
            output=job.output,
            index=index,
            result=job.result,
            time_sec=request.time_sec,
            title=request.title,
            caption_style=request.caption_style,
        )
        return {
            "ok": True,
            "thumbnail": thumbnail,
            "short": job.result["shorts"][index],
        }

    @app.get("/api/v1/jobs/{job_id}/shorts/{index}/thumbnail")
    def download_short_thumbnail(job_id: str, index: int) -> FileResponse:
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
        raw = entry.get("thumbnail") if isinstance(entry, dict) else None
        if not raw:
            raise HTTPException(
                status_code=404, detail={"ok": False, "code": "thumbnail_not_found"}
            )
        path = Path(str(raw)).expanduser().resolve()
        output = job.output.expanduser().resolve()
        if not path.is_relative_to(output) or not path.is_file():
            raise HTTPException(
                status_code=403,
                detail={"ok": False, "code": "shorts_not_allowed", "message": "outside output"},
            )
        return FileResponse(
            path,
            filename=path.name,
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/voiceover")
    def short_voiceover(
        job_id: str, index: int, request: ShortVoiceoverRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded" or job.result is None:
            raise StateNotReadyError(
                "The job must succeed before a voice-over can be generated."
            )
        state = ProjectState.model_validate_json(
            (job.output / "project_state.json").read_text(encoding="utf-8")
        )
        stored = state.modules_config.tts
        tts_provider = first_provider("tts") or {}
        tts_defaults = load_settings().tts
        config = TtsConfig(
            provider=request.provider,
            base_url=request.base_url
            or stored.base_url
            or str(tts_provider.get("base_url") or ""),
            model=request.model
            or stored.model
            or str(tts_provider.get("model") or "")
            or tts_defaults.model,
            voice=request.voice or stored.voice or tts_defaults.voice,
            secret_name=stored.secret_name
            or str(tts_provider.get("api_key_env") or "VIDEOWFLOW_TTS_API_KEY"),
            binary=request.binary or stored.binary,
            model_path=request.model_path or stored.model_path,
            speed=request.speed,
            volume=request.volume,
            original_volume=request.original_volume,
        )
        payload = generate_short_voiceover(
            output=job.output,
            index=index,
            result=job.result,
            text=request.text,
            config=config,
            api_key=get_secret(config.secret_name),
            allow_external_services=request.allow_external_services,
            allowed_external_hosts=tuple(request.allowed_external_hosts),
        )
        return {"ok": True, "voiceover": payload, "short": job.result["shorts"][index]}

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/dub")
    def short_dubbing(
        job_id: str, index: int, request: ShortDubbingRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded" or job.result is None:
            raise StateNotReadyError(
                "The job must succeed before dubbing can be generated."
            )
        state = ProjectState.model_validate_json(
            (job.output / "project_state.json").read_text(encoding="utf-8")
        )
        stored_tts = state.modules_config.tts
        tts_provider = first_provider("tts") or {}
        tts_defaults = load_settings().tts
        tts = TtsConfig(
            provider="openai_compatible",
            base_url=request.base_url
            or stored_tts.base_url
            or str(tts_provider.get("base_url") or ""),
            model=request.model
            or stored_tts.model
            or str(tts_provider.get("model") or "")
            or tts_defaults.model,
            voice=request.voice or stored_tts.voice or tts_defaults.voice,
            secret_name=stored_tts.secret_name
            or str(tts_provider.get("api_key_env") or "VIDEOWFLOW_TTS_API_KEY"),
            speed=request.speed,
            volume=request.volume,
            original_volume=request.original_volume,
        )
        dubbing = DubbingConfig(
            target_language=request.target_language,
            original_volume=request.original_volume,
        )
        payload = generate_short_dubbing(
            output=job.output,
            index=index,
            result=job.result,
            source_text=request.text,
            target_language=request.target_language,
            tts=tts,
            dubbing=dubbing,
            llm_base_url=(
                request.llm_base_url
                or state.modules_config.retakes.base_url
                or str((first_provider("llm") or {}).get("base_url") or "")
                or "http://localhost:11434/v1"
            ),
            llm_model=request.llm_model
            or state.modules_config.retakes.model_name
            or str((first_provider("llm") or {}).get("model") or ""),
            llm_api_key=get_secret("VIDEOWFLOW_LLM_API_KEY"),
            tts_api_key=get_secret(tts.secret_name),
            allow_external_services=request.allow_external_services,
            allowed_external_hosts=tuple(request.allowed_external_hosts),
        )
        return {"ok": True, "dubbing": payload, "short": job.result["shorts"][index]}

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/analyze/llm")
    def analyze_short_vision(
        job_id: str, index: int, request: ShortVisionRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded" or job.result is None:
            raise StateNotReadyError("The job must succeed before analysis.")
        vision = first_provider("vision") or {}
        base_url = (
            request.base_url
            or os.environ.get("VIDEOWFLOW_VISION_BASE_URL")
            or str(vision.get("base_url") or "")
        )
        if not base_url:
            raise CapabilityUnavailableError(
                "external_vision",
                "Configure a vision endpoint or VIDEOWFLOW_VISION_BASE_URL.",
            )
        analysis = analyze_short_llm_entry(
            output=job.output,
            index=index,
            result=job.result,
            base_url=base_url,
            model=request.model
            or str(vision.get("model") or "")
            or os.environ.get("VIDEOWFLOW_VISION_MODEL", "gpt-4o-mini"),
            api_key=get_secret(
                str(vision.get("api_key_env") or "VIDEOWFLOW_VISION_API_KEY")
            ),
            allow_external_services=request.allow_external_services,
            allowed_external_hosts=tuple(request.allowed_external_hosts),
            max_frames=request.max_frames,
        )
        return {
            "ok": True,
            "analysis": analysis,
            "short": job.result["shorts"][index],
        }

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/analyze")
    def analyze_short(job_id: str, index: int) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded" or job.result is None:
            raise StateNotReadyError("The job must succeed before analysis.")
        analysis = analyze_short_entry(
            output=job.output,
            index=index,
            result=job.result,
        )
        return {
            "ok": True,
            "analysis": analysis,
            "short": job.result["shorts"][index],
        }

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

    def fail(exc: VideoFlowError) -> None:
        raise HTTPException(status_code=status_for(exc.code), detail=exc.to_dict()) from exc

    @app.get("/api/v1/fs/roots")
    def fs_roots() -> dict[str, object]:
        return {"ok": True, "roots": roots_payload()}

    @app.get("/api/v1/fs/list")
    def fs_list(
        path: str | None = None,
        mode: Literal["file", "directory"] = "file",
        extensions: str | None = None,
        q: str = "",
        show_hidden: bool = False,
        limit: int = 500,
    ) -> dict[str, object]:
        try:
            suffixes = tuple(
                item.strip() for item in (extensions or "").split(",") if item.strip()
            )
            return {
                "ok": True,
                **list_directory(
                    path,
                    mode=mode,
                    extensions=suffixes,
                    query=q,
                    show_hidden=show_hidden,
                    limit=limit,
                ),
            }
        except VideoFlowError as exc:
            fail(exc)
        except (OSError, ValueError, OverflowError) as exc:
            fail(FilesystemError(f"Could not list this folder: {exc}"))
        except Exception as exc:  # pragma: no cover - defensive local UI boundary
            logger.exception("unhandled filesystem listing error")
            raise HTTPException(
                status_code=500,
                detail={
                    "ok": False,
                    "code": "filesystem_error",
                    "message": f"Could not list this folder: {exc}",
                },
            ) from exc

    @app.post("/api/v1/fs/mkdir", status_code=201)
    def fs_mkdir(request: NewDirectoryRequest) -> dict[str, object]:
        created = create_directory(request.parent, request.name)
        return {"ok": True, "entry": created}

    @app.get("/api/v1/media/probe")
    def media_probe(path: str) -> dict[str, object]:
        source = resolve_allowed(Path(path).expanduser(), allowed_roots())
        if not source.is_file():
            raise MediaNotFoundError(str(source))
        try:
            size = source.stat().st_size
        except OSError as exc:
            raise FilesystemError(f"Could not inspect {source}: {exc}") from exc
        media = probe_media(source)
        return {
            "ok": True,
            "path": str(source),
            "name": source.name,
            "size_bytes": size,
            "media": media.model_dump(mode="json"),
        }

    @app.post("/api/v1/media/import", status_code=201)
    def import_media(request: MediaImportRequest) -> dict[str, object]:
        path = import_url(
            request.url,
            max_height=request.max_height,
            allow_playlist=request.allow_playlist,
            allow_external_services=request.allow_external_services,
            allowed_external_hosts=tuple(request.allowed_external_hosts),
        )
        media = FFmpegAdapter().probe(path)
        return {"ok": True, "path": str(path), "media": media.model_dump(mode="json")}























    @app.post("/api/v1/copilot/recipe")
    def copilot_recipe(request: CopilotRecipeRequest) -> dict[str, object]:
        from videoflow.application.copilot import propose_recipe
        from videoflow.application.llm_factory import build_llm

        recipe = propose_recipe(build_llm(), request.prompt)
        return {"ok": True, "recipe": recipe.model_dump(mode="json")}

    @app.post("/api/v1/jobs/{job_id}/copilot/timeline")
    def copilot_timeline(
        job_id: str, request: CopilotTimelineRequest
    ) -> dict[str, object]:
        from videoflow.application.copilot import propose_timeline_edits
        from videoflow.application.llm_factory import build_llm

        job = jobs.get(job_id)
        _assert_tracks_unlocked(job, {"video", "audio"})
        state_path = _timeline_state_path(job)
        history = _timeline_history(job)
        state = ProjectState.model_validate_json(
            state_path.read_text(encoding="utf-8")
        )
        edits = propose_timeline_edits(
            build_llm(),
            request.prompt,
            [
                {
                    "id": clip.clip_id,
                    "start_sec": clip.timeline_in_frame
                    / max(0.001, (state.media_info.fps_num / state.media_info.fps_den)),
                    "end_sec": clip.timeline_out_frame
                    / max(0.001, (state.media_info.fps_num / state.media_info.fps_den)),
                }
                for clip in state.video_segments
            ],
        )
        if request.apply:
            previous = state.model_copy(deep=True)
            working = state.model_copy(deep=True)
            for item in edits:
                working = apply_timeline_edit(
                    working,
                    TimelineEdit(
                        clip_id=str(item.get("clip_id")),
                        action=str(item.get("action")),  # type: ignore[arg-type]
                        start_sec=item.get("start_sec"),
                        end_sec=item.get("end_sec"),
                        delta_sec=float(item.get("delta_sec") or 0.0),
                        split_sec=item.get("split_sec"),
                    ),
                )
            history.record(previous)
            state = _apply_and_store(
                job, working, state_path, history, previous.revision + 1
            )
        return {
            "ok": True,
            "edits": edits,
            "applied": request.apply,
            "revision": state.revision,
            "etag": _timeline_etag(state.revision),
        }

    def _assistant_timeline(state: ProjectState) -> dict[str, object]:
        media = state.media_info
        fps = (media.fps_num / media.fps_den) if media is not None else 30.0
        return {
            "revision": state.revision,
            "fps": fps,
            "video": [
                {
                    "id": clip.clip_id,
                    "start_sec": round(clip.timeline_in_frame / fps, 3),
                    "end_sec": round(clip.timeline_out_frame / fps, 3),
                    "source_in_frame": clip.source_in_frame,
                    "source_out_frame": clip.source_out_frame,
                }
                for clip in state.video_segments
            ],
        }

    def _assistant_context(job: Any) -> dict[str, object]:
        context: dict[str, object] = {
            "job": {
                "job_id": str(job.job_id),
                "status": job.status,
                "stage": job.stage,
                "source": str(job.source),
                "output": str(job.output),
            },
            "recipes": [
                {"id": item.get("id"), "name": item.get("name")}
                for item in list_recipes()[:40]
            ],
        }
        try:
            state = ProjectState.model_validate_json(
                _timeline_state_path(job).read_text(encoding="utf-8")
            )
            context["timeline"] = _assistant_timeline(state)
        except (OSError, ValueError, StateNotReadyError):
            context["timeline"] = None
        return context

    def _assistant_read(job: Any, action: Any) -> dict[str, object]:
        if action.tool == "list_recipes":
            return {"tool": action.id, "recipes": list_recipes()[:80]}
        if action.tool == "get_job":
            payload = job.to_dict()
            payload.pop("result", None)
            payload.pop("options", None)
            return {"tool": action.id, "job": payload}
        if action.tool == "get_timeline":
            state = ProjectState.model_validate_json(
                _timeline_state_path(job).read_text(encoding="utf-8")
            )
            return {"tool": action.id, "timeline": _assistant_timeline(state)}
        if action.tool == "validate_exports":
            return {
                "tool": action.id,
                "validation": validate_nle_exports(job.output / "nle"),
            }
        return {"tool": action.id, "skipped": "not read-only"}

    @app.post("/api/v1/jobs/{job_id}/assistant")
    def assistant_turn(
        job_id: str, request: AssistantRequest
    ) -> dict[str, object]:
        from videoflow.application import assistant
        from videoflow.application.cost import snapshot as cost_snapshot
        from videoflow.application.llm_factory import build_llm

        job = jobs.get(job_id)
        context = _assistant_context(job)
        before = cost_snapshot()
        client = build_llm()
        turn = assistant.plan(client, prompt=request.prompt, context=context)
        observations: list[dict[str, object]] = []
        if turn.actions and all(not item.writes for item in turn.actions):
            observations = [_assistant_read(job, item) for item in turn.actions]
            turn = assistant.plan(
                client,
                prompt=request.prompt,
                context=context,
                observations=observations,
            )
        writes = [item for item in turn.actions if item.writes]
        diff: list[dict[str, Any]] = []
        if writes:
            state = ProjectState.model_validate_json(
                _timeline_state_path(job).read_text(encoding="utf-8")
            )
            before_timeline = _assistant_timeline(state)
            working = state.model_copy(deep=True)
            for action in writes:
                if action.tool != "apply_timeline_edits":
                    continue
                for item in action.arguments.get("edits", []):
                    working = apply_timeline_edit(
                        working,
                        TimelineEdit(
                            clip_id=str(item.get("clip_id")),
                            action=str(item.get("action")),  # type: ignore[arg-type]
                            start_sec=item.get("start_sec"),
                            end_sec=item.get("end_sec"),
                            delta_sec=float(item.get("delta_sec") or 0.0),
                            split_sec=item.get("split_sec"),
                        ),
                    )
            diff = assistant.diff_timeline(
                before_timeline, _assistant_timeline(working)
            )
        after = cost_snapshot()
        approval_id = ""
        if writes:
            import uuid

            approval_id = f"approval-{uuid.uuid4().hex[:10]}"
            assistant.save_pending(
                job.output,
                assistant.PendingPlan(
                    approval_id=approval_id,
                    job_id=str(job.job_id),
                    prompt=request.prompt,
                    message=turn.message,
                    actions=writes,
                    diff=diff,
                    created_at=assistant.now(),
                ),
            )
            assistant.record_history(
                job.output,
                assistant.HistoryEntry(
                    at=assistant.now(),
                    job_id=str(job.job_id),
                    prompt=request.prompt,
                    message=turn.message,
                    actions=[item.model_dump(mode="json") for item in writes],
                    applied=False,
                    approval_id=approval_id,
                    tokens=int(after.get("prompt_tokens", 0))
                    + int(after.get("completion_tokens", 0))
                    - int(before.get("prompt_tokens", 0))
                    - int(before.get("completion_tokens", 0)),
                    cost_usd=round(
                        float(after.get("estimated_cost_usd", 0.0))
                        - float(before.get("estimated_cost_usd", 0.0)),
                        6,
                    ),
                ),
            )
        token_delta = (
            int(after.get("prompt_tokens", 0))
            + int(after.get("completion_tokens", 0))
            - int(before.get("prompt_tokens", 0))
            - int(before.get("completion_tokens", 0))
        )
        cost_delta = round(
            float(after.get("estimated_cost_usd", 0.0))
            - float(before.get("estimated_cost_usd", 0.0)),
            6,
        )
        return {
            "ok": True,
            "message": turn.message,
            "actions": [item.model_dump(mode="json") for item in turn.actions],
            "observations": observations,
            "diff": diff,
            "requires_approval": bool(writes),
            "approval_id": approval_id,
            "tokens": token_delta,
            "cost_usd": cost_delta,
            "budget_usd": after.get("budget_usd", 0.0),
            "remaining_usd": after.get("remaining_usd"),
        }

    def _assistant_apply(job: Any, action: Any) -> dict[str, object]:
        if action.tool == "apply_timeline_edits":
            _assert_tracks_unlocked(job, {"video", "audio"})
            state_path = _timeline_state_path(job)
            history = _timeline_history(job)
            previous = ProjectState.model_validate_json(
                state_path.read_text(encoding="utf-8")
            )
            working = previous.model_copy(deep=True)
            for item in action.arguments.get("edits", []):
                working = apply_timeline_edit(
                    working,
                    TimelineEdit(
                        clip_id=str(item.get("clip_id")),
                        action=str(item.get("action")),  # type: ignore[arg-type]
                        start_sec=item.get("start_sec"),
                        end_sec=item.get("end_sec"),
                        delta_sec=float(item.get("delta_sec") or 0.0),
                        split_sec=item.get("split_sec"),
                    ),
                )
            history.record(previous)
            applied = _apply_and_store(
                job, working, state_path, history, previous.revision + 1
            )
            return {
                "tool": action.id,
                "applied": True,
                "revision": applied.revision,
                "etag": _timeline_etag(applied.revision),
            }
        if action.tool == "render_preview":
            preview = previews.start(job)
            return {"tool": action.id, "preview": preview.to_dict()}
        if action.tool == "run_recipe":
            payload = RecipeRunRequest(
                recipe_id=str(action.arguments.get("recipe_id")),
                source=str(action.arguments.get("source")),
                output=str(action.arguments.get("output")),
                variables=dict(action.arguments.get("variables") or {}),
            )
            return {"tool": action.id, **start_recipe_job(payload, None, jobs)}
        raise StateNotReadyError(f"Unsupported write tool: {action.tool}")

    @app.post("/api/v1/jobs/{job_id}/assistant/approve")
    def assistant_approve(
        job_id: str, request: AssistantApprovalRequest
    ) -> dict[str, object]:
        from videoflow.application import assistant

        job = jobs.get(job_id)
        pending = assistant.load_pending(job.output, request.approval_id)
        if pending.job_id != str(job.job_id):
            raise StateNotReadyError("The approval belongs to another job.")
        results = [_assistant_apply(job, action) for action in pending.actions]
        assistant.delete_pending(job.output, request.approval_id)
        assistant.record_history(
            job.output,
            assistant.HistoryEntry(
                at=assistant.now(),
                job_id=str(job.job_id),
                prompt=pending.prompt,
                message=pending.message,
                actions=[item.model_dump(mode="json") for item in pending.actions],
                applied=True,
                approval_id=pending.approval_id,
            ),
        )
        return {"ok": True, "approval_id": request.approval_id, "results": results}

    @app.get("/api/v1/jobs/{job_id}/assistant/history")
    def assistant_history(job_id: str) -> dict[str, object]:
        from videoflow.application import assistant

        job = jobs.get(job_id)
        return {"ok": True, "history": assistant.read_history(job.output)}




    def _plugins_payload(items: list[dict[str, object]]) -> dict[str, object]:
        from videoflow import plugin_api

        return {
            "ok": True,
            "plugins": items,
            "panels": [
                {"id": key, **value} for key, value in plugin_api.PANELS.items()
            ],
        }













def probe_media(path: Path) -> MediaInfo:
    return FFmpegAdapter().probe(path)
