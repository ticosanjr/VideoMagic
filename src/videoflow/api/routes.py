"""Project and job routes for the local API."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError, model_validator

from videoflow import __version__
from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.brand_templates import (
    BrandTemplate,
    apply_brand_options,
    delete_template,
    get_template,
    list_templates,
    save_template,
)
from videoflow.application.capabilities import (
    capability_manifest,
    external_services_allowed,
)
from videoflow.application.caption_ai import apply_llm_emoji
from videoflow.application.dubbing import generate_short_dubbing
from videoflow.application.export_service import export_timeline
from videoflow.application.filesystem import create_directory, list_directory, roots_payload
from videoflow.application.fonts import list_fonts, save_font
from videoflow.application.images import list_images, save_image
from videoflow.application.jobs import TERMINAL, Job, JobManager
from videoflow.application.models import install_model, list_models, remove_model
from videoflow.application.multimodal import analyze_short_entry
from videoflow.application.multimodal_llm import analyze_short_llm_entry
from videoflow.application.music import list_music, save_music
from videoflow.application.nle_validation import validate_nle_exports
from videoflow.application.presets import get_preset, load_presets, save_preset
from videoflow.application.project_templates import (
    ProjectTemplate,
    export_config,
    import_config,
    sanitize_options,
)
from videoflow.application.project_templates import (
    delete_template as delete_project_template,
)
from videoflow.application.project_templates import (
    get_template as get_project_template,
)
from videoflow.application.project_templates import (
    list_templates as list_project_templates,
)
from videoflow.application.project_templates import (
    save_template as save_project_template,
)
from videoflow.application.projects import (
    ProjectStore,
    apply_media,
    apply_module_config,
    apply_module_enabled,
    apply_overrides,
    apply_preset,
)
from videoflow.application.publishing import (
    PublishTarget,
    cancel_publish,
    delete_target,
    dispatch_due,
    enqueue_publish,
    list_queue,
    list_targets,
    save_target,
)
from videoflow.application.runner import PipelineRunner
from videoflow.application.services import (
    append_server_log,
    discover_services,
    read_server_log,
    server_log_path,
    stop_other_services,
    stop_service_pid,
)
from videoflow.application.short_editor import ShortEditOptions
from videoflow.application.short_editor import edit_short as edit_short_service
from videoflow.application.short_metadata import generate_short_metadata
from videoflow.application.thumbnail import generate_short_thumbnail
from videoflow.application.url_import import import_url
from videoflow.application.voiceover import generate_short_voiceover
from videoflow.core.recipe import parse_recipe, recipe_to_dict
from videoflow.domain.config import (
    DubbingConfig,
    MediaLanguage,
    ModuleEnabled,
    TtsConfig,
)
from videoflow.domain.errors import (
    CapabilityUnavailableError,
    FilesystemError,
    JobAlreadyRunningError,
    JobNotFoundError,
    MediaNotFoundError,
    MediaNotRegisteredError,
    ModuleBypassedError,
    RecipeError,
    StateNotReadyError,
    TranscriptNotFoundError,
    TranscriptRequiredError,
    UnknownModuleError,
    VideoFlowError,
)
from videoflow.domain.paths import resolve_allowed
from videoflow.domain.state import ManualOverride, MediaInfo, ProjectState
from videoflow.domain.transcript import format_srt
from videoflow.engine.batch import BatchManager
from videoflow.engine.history import read_runs
from videoflow.engine.maintenance import prune_output
from videoflow.engine.recipes import (
    get_recipe,
    list_recipes,
    resolve_recipe_paths,
    save_user_recipe,
)
from videoflow.runtime import allowed_roots, find_binary, portable_home
from videoflow.steps import manifest as step_manifest
from videoflow.steps import requirements_by_type, step_types

logger = logging.getLogger(__name__)


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


class RecipeRunRequest(BaseModel):
    source: str = Field(min_length=1)
    output: str = Field(min_length=1)
    recipe: dict[str, Any] | None = None
    recipe_id: str | None = None
    transcript_sentences: list[dict[str, Any]] = Field(default_factory=list)
    save_recipe: bool = False
    through: str | None = None
    resume: bool = True

    @model_validator(mode="after")
    def exactly_one_recipe(self) -> RecipeRunRequest:
        if (self.recipe is None) == (self.recipe_id is None):
            raise ValueError("provide exactly one of recipe or recipe_id")
        return self


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


class NewProjectRequest(BaseModel):
    root: str = Field(min_length=1)
    preset: str | None = None


class MediaRequest(BaseModel):
    file_path: str = Field(min_length=1)


class MediaImportRequest(BaseModel):
    url: str = Field(min_length=1)
    max_height: int = Field(default=1080, ge=144, le=4320)
    allow_playlist: bool = False
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)


class NewDirectoryRequest(BaseModel):
    parent: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=255)


class EnabledRequest(BaseModel):
    enabled: bool


class ProjectRunRequest(BaseModel):
    run_upstream: bool = False
    force: bool = False


class ExportRequest(BaseModel):
    targets: list[Literal["resolve", "premiere", "kdenlive"]] | None = None
    dialect: Literal["1.9", "1.10"] | None = None


class PublishTargetRequest(BaseModel):
    description: str = ""
    webhook_url: str = Field(min_length=1)
    secret_name: str = "VIDEOWFLOW_PUBLISH_TOKEN"
    enabled: bool = True


class PublishShortRequest(BaseModel):
    target: str = Field(min_length=1)
    platform: Literal["youtube", "tiktok", "instagram", "linkedin"] = "youtube"
    tone: Literal["engaging", "professional", "educational", "bold"] = "engaging"
    scheduled_at: str | None = None
    extra_hashtags: list[str] = Field(default_factory=list)
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)


class PublishDispatchRequest(BaseModel):
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)


class ConfigExportRequest(BaseModel):
    options: dict[str, Any] = Field(default_factory=dict)


class ConfigImportRequest(BaseModel):
    schema_version: int
    options: dict[str, Any] = Field(default_factory=dict)


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


class ExportValidationRequest(BaseModel):
    output: str = Field(min_length=1)


class MaintenancePruneRequest(BaseModel):
    output: str = Field(min_length=1)
    keep_days: int = Field(default=14, ge=1, le=3650)
    keep_steps: int = Field(default=200, ge=1, le=10000)
    keep_runs: int = Field(default=30, ge=1, le=1000)
    dry_run: bool = False


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


class ModelInstallRequest(BaseModel):
    allow_external_services: bool = True


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
    app: FastAPI,
    jobs: JobManager,
    projects: ProjectStore,
    batches: BatchManager | None = None,
) -> None:
    project_job_lock = threading.Lock()
    app.state.project_store = projects
    batch_manager = batches or BatchManager(jobs)
    app.state.batches = batch_manager

    def start_recipe_job(request: RecipeRunRequest, through: str | None) -> dict[str, object]:
        roots = allowed_roots()
        source = resolve_allowed(Path(request.source), roots)
        output = resolve_allowed(Path(request.output), roots)
        if request.recipe is not None:
            recipe = parse_recipe(request.recipe)
        else:
            recipe = get_recipe(str(request.recipe_id))
        recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
        if through is not None and through not in {step.id for step in recipe.enabled_steps()}:
            raise RecipeError(f"Unknown or disabled step: {through}")
        recipe = resolve_recipe_paths(recipe, roots)
        if request.save_recipe:
            save_user_recipe(recipe)
        job = jobs.start(
            source,
            output,
            {
                "mode": "recipe",
                "recipe": recipe.model_dump(mode="json"),
                "transcript_sentences": request.transcript_sentences,
                "through": through,
                "resume": request.resume,
            },
        )
        return {"ok": True, "job": job.to_dict()}

    @app.get("/api/v1/assets/music")
    def music() -> dict[str, object]:
        return {"ok": True, "music": list_music()}

    @app.post("/api/v1/assets/music", status_code=201)
    async def upload_music(name: str, request: Request) -> dict[str, object]:
        try:
            asset = save_music(name, await request.body())
        except FilesystemError as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "music_invalid", "message": str(exc)},
            ) from exc
        return {"ok": True, "music": asset}

    @app.get("/api/v1/assets/images")
    def images() -> dict[str, object]:
        return {"ok": True, "images": list_images()}

    @app.post("/api/v1/assets/images", status_code=201)
    async def upload_image(name: str, request: Request) -> dict[str, object]:
        try:
            asset = save_image(name, await request.body())
        except FilesystemError as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "image_invalid", "message": str(exc)},
            ) from exc
        return {"ok": True, "image": asset}

    @app.get("/api/v1/assets/fonts")
    def fonts() -> dict[str, object]:
        return {"ok": True, "fonts": list_fonts()}

    @app.post("/api/v1/assets/fonts", status_code=201)
    async def upload_font(name: str, request: Request) -> dict[str, object]:
        try:
            asset = save_font(name, await request.body())
        except FilesystemError as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "font_invalid", "message": str(exc)},
            ) from exc
        return {"ok": True, "font": asset}

    @app.get("/api/v1/capabilities")
    def capabilities(allow_external: bool = False) -> dict[str, object]:
        return {
            "ok": True,
            "external_services_allowed": external_services_allowed(allow_external),
            "capabilities": capability_manifest(allow_external_services=allow_external),
        }

    @app.get("/api/v1/steps")
    def list_steps() -> dict[str, object]:
        return {"ok": True, "steps": step_manifest()}

    @app.get("/api/v1/recipes")
    def recipes() -> dict[str, object]:
        return {"ok": True, "recipes": list_recipes()}

    @app.get("/api/v1/recipes/{recipe_id}")
    def recipe_detail(recipe_id: str) -> dict[str, object]:
        try:
            recipe = get_recipe(recipe_id)
        except VideoFlowError as exc:
            fail(exc)
            raise
        return {"ok": True, "recipe": recipe_to_dict(recipe)}

    @app.put("/api/v1/recipes/{recipe_id}")
    def save_recipe(recipe_id: str, payload: dict[str, Any]) -> dict[str, object]:
        try:
            recipe = parse_recipe(payload)
            if recipe.id != recipe_id:
                raise RecipeError("recipe id does not match the URL")
            recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
            path = save_user_recipe(recipe)
        except VideoFlowError as exc:
            fail(exc)
            raise
        return {"ok": True, "recipe": recipe_to_dict(recipe), "path": str(path)}

    @app.post("/api/v1/recipes/validate")
    def validate_recipe(payload: dict[str, Any]) -> dict[str, object]:
        try:
            recipe = parse_recipe(payload)
            recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
            order = recipe.topological_order()
        except VideoFlowError as exc:
            fail(exc)
            raise
        return {
            "ok": True,
            "recipe": recipe_to_dict(recipe),
            "order": [step.id for step in order],
        }

    @app.post("/api/v1/recipes/run", status_code=202)
    def run_recipe(request: RecipeRunRequest) -> dict[str, object]:
        try:
            return start_recipe_job(request, request.through)
        except VideoFlowError as exc:
            fail(exc)
            raise

    @app.post("/api/v1/steps/{step_id}/run", status_code=202)
    def run_step(step_id: str, request: RecipeRunRequest) -> dict[str, object]:
        try:
            return start_recipe_job(request, step_id)
        except VideoFlowError as exc:
            fail(exc)
            raise

    @app.post("/api/v1/batches", status_code=202)
    def create_batch(request: BatchRequest) -> dict[str, object]:
        roots = allowed_roots()
        try:
            source_dir = resolve_allowed(Path(request.source_dir), roots)
            output_root = resolve_allowed(Path(request.output_root), roots)
            if request.recipe is not None:
                recipe = parse_recipe(request.recipe)
            else:
                recipe = get_recipe(str(request.recipe_id))
            recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
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
        except VideoFlowError as exc:
            fail(exc)
            raise
        return {"ok": True, "batch": batch.to_dict()}

    @app.post("/api/v1/maintenance/prune")
    def maintenance_prune(request: MaintenancePruneRequest) -> dict[str, object]:
        try:
            resolved = resolve_allowed(Path(request.output), allowed_roots())
            if not resolved.is_dir():
                raise FilesystemError(f"Output directory does not exist: {resolved}")
        except VideoFlowError as exc:
            fail(exc)
            raise
        return prune_output(
            resolved,
            keep_days=request.keep_days,
            keep_steps=request.keep_steps,
            keep_runs=request.keep_runs,
            dry_run=request.dry_run,
        )

    @app.post("/api/v1/exports/validate")
    def validate_exports(request: ExportValidationRequest) -> dict[str, object]:
        try:
            resolved = resolve_allowed(Path(request.output), allowed_roots())
            directory = (
                resolved
                if (resolved / "timeline.fcpxml").is_file()
                else resolved / "exports"
            )
            if not directory.is_dir():
                raise FilesystemError(f"Export directory does not exist: {directory}")
        except VideoFlowError as exc:
            fail(exc)
            raise
        return validate_nle_exports(directory)

    @app.get("/api/v1/runs")
    def list_runs(output: str) -> dict[str, object]:
        try:
            resolved = resolve_allowed(Path(output), allowed_roots())
        except VideoFlowError as exc:
            fail(exc)
            raise
        return {"ok": True, "runs": read_runs(resolved)}

    @app.get("/api/v1/batches")
    def list_batches() -> dict[str, object]:
        return {
            "ok": True,
            "batches": [batch.to_dict() for batch in batch_manager.list()],
        }

    @app.post("/api/v1/batches/{batch_id}/resume")
    def resume_batch(batch_id: str) -> dict[str, object]:
        try:
            batch = batch_manager.resume(batch_id)
        except VideoFlowError as exc:
            fail(exc)
        return {"ok": True, "batch": batch.to_dict()}

    @app.get("/api/v1/batches/{batch_id}")
    def get_batch(batch_id: str) -> dict[str, object]:
        try:
            batch = batch_manager.get(batch_id)
        except VideoFlowError as exc:
            fail(exc)
            raise
        return {"ok": True, "batch": batch.to_dict()}

    @app.post("/api/v1/batches/{batch_id}/cancel")
    def cancel_batch(batch_id: str) -> dict[str, object]:
        try:
            batch = batch_manager.cancel(batch_id)
        except VideoFlowError as exc:
            fail(exc)
            raise
        return {"ok": True, "batch": batch.to_dict()}

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
            job = jobs.start(source, output, options=options)
        except VideoFlowError as exc:
            raise HTTPException(status_code=status_for(exc.code), detail=exc.to_dict()) from exc
        return {"ok": True, "job": job.to_dict()}

    @app.get("/api/v1/publish/targets")
    def publish_targets() -> dict[str, object]:
        return {"ok": True, "targets": list_targets()}

    @app.put("/api/v1/publish/targets/{name}")
    def put_publish_target(name: str, request: PublishTargetRequest) -> dict[str, object]:
        return {
            "ok": True,
            "target": save_target(
                PublishTarget(name=name, **request.model_dump())
            ),
        }

    @app.delete("/api/v1/publish/targets/{name}")
    def remove_publish_target(name: str) -> dict[str, object]:
        delete_target(name)
        return {"ok": True, "deleted": name}

    @app.get("/api/v1/publish/queue")
    def publish_queue() -> dict[str, object]:
        return {"ok": True, "items": list_queue()}

    @app.post("/api/v1/publish/queue/{item_id}/cancel")
    def cancel_publish_item(item_id: str) -> dict[str, object]:
        try:
            return {"ok": True, "item": cancel_publish(item_id)}
        except VideoFlowError as exc:
            fail(exc)

    @app.post("/api/v1/publish/dispatch")
    def publish_dispatch(request: PublishDispatchRequest) -> dict[str, object]:
        items = dispatch_due(
            allow_external_services=request.allow_external_services,
            allowed_hosts=tuple(request.allowed_external_hosts),
        )
        return {"ok": True, "items": items}

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/publish")
    def publish_short(
        job_id: str, index: int, request: PublishShortRequest
    ) -> dict[str, object]:
        try:
            job = jobs.get(job_id)
            if job.status != "succeeded" or job.result is None:
                raise StateNotReadyError(
                    "The job must succeed before a Short can be published."
                )
            shorts = job.result.get("shorts")
            if not isinstance(shorts, list) or index < 0 or index >= len(shorts):
                raise StateNotReadyError("Short index is out of range.")
            entry = shorts[index]
            if not isinstance(entry, dict) or not entry.get("path"):
                raise StateNotReadyError("Short asset is missing.")
            metadata = generate_short_metadata(
                output=job.output,
                index=index,
                result=job.result,
                platform=request.platform,
                tone=request.tone,
                extra_hashtags=tuple(request.extra_hashtags),
            )
            item = enqueue_publish(
                target_name=request.target,
                asset_path=Path(str(entry["path"])),
                title=str(metadata["title"]),
                description=str(metadata["description"]),
                hashtags=[str(tag) for tag in metadata["hashtags"]],
                platform=request.platform,
                scheduled_at=request.scheduled_at,
                job_id=job_id,
                short_index=index,
            )
        except VideoFlowError as exc:
            fail(exc)
        return {"ok": True, "item": item}

    @app.get("/api/v1/project-templates")
    def project_templates() -> dict[str, object]:
        return {"ok": True, "templates": list_project_templates()}

    @app.get("/api/v1/project-templates/{name}")
    def project_template(name: str) -> dict[str, object]:
        try:
            return {
                "ok": True,
                "template": get_project_template(name).model_dump(mode="json"),
            }
        except VideoFlowError as exc:
            fail(exc)

    @app.put("/api/v1/project-templates/{name}")
    def put_project_template(name: str, template: ProjectTemplate) -> dict[str, object]:
        try:
            payload = save_project_template(template.model_copy(update={"name": name}))
        except VideoFlowError as exc:
            fail(exc)
        return {"ok": True, "template": payload}

    @app.delete("/api/v1/project-templates/{name}")
    def remove_project_template(name: str) -> dict[str, object]:
        try:
            delete_project_template(name)
        except VideoFlowError as exc:
            fail(exc)
        return {"ok": True, "deleted": name}

    @app.post("/api/v1/project-templates/{name}/apply")
    def apply_project_template(name: str) -> dict[str, object]:
        try:
            options = get_project_template(name).options
        except VideoFlowError as exc:
            fail(exc)
        return {"ok": True, "options": sanitize_options(options)}

    @app.post("/api/v1/config/export")
    def config_export(request: ConfigExportRequest) -> dict[str, object]:
        return {"ok": True, "envelope": export_config(request.options)}

    @app.post("/api/v1/config/import")
    def config_import(request: ConfigImportRequest) -> dict[str, object]:
        try:
            options = import_config(
                {"schema_version": request.schema_version, "options": request.options}
            )
        except VideoFlowError as exc:
            fail(exc)
        return {"ok": True, "options": options}

    @app.get("/api/v1/brand-templates")
    def brand_templates() -> dict[str, object]:
        return {"ok": True, "templates": list_templates()}

    @app.get("/api/v1/brand-templates/{name}")
    def brand_template(name: str) -> dict[str, object]:
        try:
            return {"ok": True, "template": get_template(name).model_dump(mode="json")}
        except VideoFlowError as exc:
            fail(exc)

    @app.put("/api/v1/brand-templates/{name}")
    def put_brand_template(name: str, template: BrandTemplate) -> dict[str, object]:
        try:
            payload = save_template(template.model_copy(update={"name": name}))
        except VideoFlowError as exc:
            fail(exc)
        return {"ok": True, "template": payload}

    @app.delete("/api/v1/brand-templates/{name}")
    def remove_brand_template(name: str) -> dict[str, object]:
        try:
            delete_template(name)
        except VideoFlowError as exc:
            fail(exc)
        return {"ok": True, "deleted": name}

    @app.post("/api/v1/brand-templates/{name}/apply")
    def apply_brand_template(name: str) -> dict[str, object]:
        try:
            options = apply_brand_options({}, name)
        except VideoFlowError as exc:
            fail(exc)
        return {"ok": True, "options": options}

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

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/edit")
    def edit_short(
        job_id: str, index: int, request: ShortEditRequest
    ) -> dict[str, object]:
        try:
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
        except VideoFlowError as exc:
            fail(exc)
        return {
            "ok": True,
            "short": entry,
            "download": f"/api/v1/jobs/{job_id}/shorts/{index}",
        }

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/captions/emoji")
    def short_emoji(
        job_id: str, index: int, request: ShortEmojiRequest
    ) -> dict[str, object]:
        try:
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
        except VideoFlowError as exc:
            fail(exc)
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
        try:
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
        except VideoFlowError as exc:
            fail(exc)
        return {
            "ok": True,
            "metadata": metadata,
            "short": job.result["shorts"][index],
        }

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
        try:
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
        except VideoFlowError as exc:
            fail(exc)
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
        try:
            job = jobs.get(job_id)
            if job.status != "succeeded" or job.result is None:
                raise StateNotReadyError(
                    "The job must succeed before a voice-over can be generated."
                )
            state = ProjectState.model_validate_json(
                (job.output / "project_state.json").read_text(encoding="utf-8")
            )
            stored = state.modules_config.tts
            config = TtsConfig(
                provider=request.provider,
                base_url=request.base_url or stored.base_url,
                model=request.model or stored.model,
                voice=request.voice or stored.voice,
                secret_name=stored.secret_name,
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
                api_key=os.environ.get(config.secret_name),
                allow_external_services=request.allow_external_services,
                allowed_external_hosts=tuple(request.allowed_external_hosts),
            )
        except VideoFlowError as exc:
            fail(exc)
        return {"ok": True, "voiceover": payload, "short": job.result["shorts"][index]}

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/dub")
    def short_dubbing(
        job_id: str, index: int, request: ShortDubbingRequest
    ) -> dict[str, object]:
        try:
            job = jobs.get(job_id)
            if job.status != "succeeded" or job.result is None:
                raise StateNotReadyError(
                    "The job must succeed before dubbing can be generated."
                )
            state = ProjectState.model_validate_json(
                (job.output / "project_state.json").read_text(encoding="utf-8")
            )
            stored_tts = state.modules_config.tts
            tts = TtsConfig(
                provider="openai_compatible",
                base_url=request.base_url or stored_tts.base_url,
                model=request.model or stored_tts.model,
                voice=request.voice or stored_tts.voice,
                secret_name=stored_tts.secret_name,
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
                    or "http://localhost:11434/v1"
                ),
                llm_model=request.llm_model or state.modules_config.retakes.model_name,
                llm_api_key=os.environ.get("VIDEOWFLOW_LLM_API_KEY"),
                tts_api_key=os.environ.get(tts.secret_name),
                allow_external_services=request.allow_external_services,
                allowed_external_hosts=tuple(request.allowed_external_hosts),
            )
        except VideoFlowError as exc:
            fail(exc)
        return {"ok": True, "dubbing": payload, "short": job.result["shorts"][index]}

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/analyze/llm")
    def analyze_short_vision(
        job_id: str, index: int, request: ShortVisionRequest
    ) -> dict[str, object]:
        try:
            job = jobs.get(job_id)
            if job.status != "succeeded" or job.result is None:
                raise StateNotReadyError("The job must succeed before analysis.")
            base_url = request.base_url or os.environ.get("VIDEOWFLOW_VISION_BASE_URL")
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
                model=request.model or os.environ.get(
                    "VIDEOWFLOW_VISION_MODEL", "gpt-4o-mini"
                ),
                api_key=os.environ.get("VIDEOWFLOW_VISION_API_KEY"),
                allow_external_services=request.allow_external_services,
                allowed_external_hosts=tuple(request.allowed_external_hosts),
                max_frames=request.max_frames,
            )
        except VideoFlowError as exc:
            fail(exc)
        return {
            "ok": True,
            "analysis": analysis,
            "short": job.result["shorts"][index],
        }

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/analyze")
    def analyze_short(job_id: str, index: int) -> dict[str, object]:
        try:
            job = jobs.get(job_id)
            if job.status != "succeeded" or job.result is None:
                raise StateNotReadyError("The job must succeed before analysis.")
            analysis = analyze_short_entry(
                output=job.output,
                index=index,
                result=job.result,
            )
        except VideoFlowError as exc:
            fail(exc)
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

    @app.post("/api/v1/projects/{project_id}/modules/{module_id}/run", status_code=202)
    def run_module(project_id: UUID, module_id: str) -> dict[str, object]:
        try:
            record = projects.get(project_id)
            if module_id not in ModuleEnabled.model_fields:
                raise UnknownModuleError(module_id)
            state = projects.read_state(project_id)
            media = state.media_info
            if media is None:
                raise MediaNotRegisteredError("Register source media before running.")
            source = resolve_allowed(Path(media.source_path), allowed_roots())
            if not source.is_file():
                raise MediaNotFoundError(str(source))
            status = _project_module_status(record, state)
            plan = PipelineRunner().plan(
                status,
                target=module_id,
                run_upstream=True,
                enabled=state.module_enabled.model_dump(),
            )
            if not plan.modules:
                return {
                    "ok": True,
                    "job": None,
                    "mode": "cached",
                    "module_id": module_id,
                    "planned": [],
                    "skipped": list(plan.skipped),
                }
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
        return {
            "ok": True,
            "job": job.to_dict(),
            "mode": "full_pipeline",
            "module_id": module_id,
            "planned": list(plan.modules),
            "skipped": list(plan.skipped),
            "message": (
                "The legacy project pipeline reruns the full graph; recipe runs "
                "use per-step checkpoints."
            ),
        }

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

    @app.get("/api/v1/fs/roots")
    def fs_roots() -> dict[str, object]:
        try:
            return {"ok": True, "roots": roots_payload()}
        except VideoFlowError as exc:
            fail(exc)

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
        try:
            created = create_directory(request.parent, request.name)
            return {"ok": True, "entry": created}
        except VideoFlowError as exc:
            fail(exc)

    @app.get("/api/v1/media/probe")
    def media_probe(path: str) -> dict[str, object]:
        try:
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
        except VideoFlowError as exc:
            fail(exc)

    @app.post("/api/v1/media/import", status_code=201)
    def import_media(request: MediaImportRequest) -> dict[str, object]:
        try:
            path = import_url(
                request.url,
                max_height=request.max_height,
                allow_playlist=request.allow_playlist,
                allow_external_services=request.allow_external_services,
                allowed_external_hosts=tuple(request.allowed_external_hosts),
            )
            media = FFmpegAdapter().probe(path)
        except VideoFlowError as exc:
            fail(exc)
        return {"ok": True, "path": str(path), "media": media.model_dump(mode="json")}

    @app.get("/api/v1/services")
    def services_list(request: Request) -> dict[str, object]:
        services = [
            item.to_dict()
            for item in discover_services(current_pid=os.getpid())
            if item.kind != "launcher"
        ]
        return {
            "ok": True,
            "pid": os.getpid(),
            "port": getattr(request.app.state, "port", None),
            "log_path": str(server_log_path()),
            "services": services,
        }

    @app.get("/api/v1/services/log")
    def services_log(lines: int = 200) -> dict[str, object]:
        return {
            "ok": True,
            "path": str(server_log_path()),
            "text": read_server_log(lines),
        }

    @app.post("/api/v1/services/cleanup")
    def services_cleanup() -> dict[str, object]:
        result = stop_other_services(current_pid=os.getpid())
        append_server_log(f"cleanup result={result}")
        return {"ok": True, **result}

    @app.post("/api/v1/services/{pid}/stop")
    def services_stop(pid: int) -> dict[str, object]:
        services = {
            item.pid: item for item in discover_services(current_pid=os.getpid())
        }
        target = services.get(pid)
        if target is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "service_not_found",
                    "message": f"VideoFlow service {pid} was not found.",
                },
            )
        if target.current or target.protected:
            raise HTTPException(
                status_code=409,
                detail={
                    "ok": False,
                    "code": "service_protected",
                    "message": "Use Stop service for the current process.",
                },
            )
        stopped = stop_service_pid(pid)
        append_server_log(f"stop requested pid={pid} stopped={stopped}")
        return {"ok": True, "stopped": stopped, "pid": pid}

    @app.post("/api/v1/system/restart")
    def system_restart(request: Request) -> dict[str, object]:
        server = getattr(request.app.state, "uvicorn_server", None)
        if server is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "ok": False,
                    "code": "service_control_unavailable",
                    "message": "Service controls are only available in the desktop server.",
                },
            )
        request.app.state.restart_requested = True
        server.should_exit = True
        return {"ok": True, "action": "restart"}

    @app.post("/api/v1/system/shutdown")
    def system_shutdown(request: Request) -> dict[str, object]:
        server = getattr(request.app.state, "uvicorn_server", None)
        if server is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "ok": False,
                    "code": "service_control_unavailable",
                    "message": "Service controls are only available in the desktop server.",
                },
            )
        request.app.state.restart_requested = False
        server.should_exit = True
        return {"ok": True, "action": "shutdown"}

    @app.get("/api/v1/models")
    def models_list() -> dict[str, object]:
        return {"ok": True, "models": list_models()}

    @app.post("/api/v1/models/{model_id}/install")
    def models_install(
        model_id: str, request: ModelInstallRequest | None = None
    ) -> dict[str, object]:
        try:
            payload = install_model(
                model_id,
                allow_network=True
                if request is None
                else request.allow_external_services,
            )
        except VideoFlowError as exc:
            fail(exc)
        return {"ok": True, "model": payload}

    @app.delete("/api/v1/models/{model_id}")
    def models_remove(model_id: str) -> dict[str, object]:
        try:
            remove_model(model_id)
        except VideoFlowError as exc:
            fail(exc)
        return {"ok": True, "removed": model_id}

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


def _project_module_status(record, state) -> dict[str, str]:
    """Approximate the rack module cache from the persisted project state."""

    timeline = bool(state.video_segments and state.audio_segments)
    exports = record.videoflow_dir / "exports"
    return {
        "ingest": "cached" if state.media_info is not None else "missing",
        "vad": "cached" if state.vad_intervals else "missing",
        "transcribe": "cached" if state.transcript else "missing",
        "retakes": "cached" if state.transcript else "missing",
        "jl_cuts": "cached" if timeline else "missing",
        "zooms": "cached" if timeline else "missing",
        "shorts": "cached" if (record.videoflow_dir / "shorts.json").is_file() else "missing",
        "export": "cached" if exports.is_dir() and any(exports.iterdir()) else "missing",
    }


def status_for(code: str) -> int:
    return {
        "path_not_allowed": 403,
        "path_not_found": 404,
        "not_a_directory": 422,
        "directory_exists": 409,
        "invalid_directory_name": 422,
        "permission_denied": 403,
        "filesystem_error": 500,
        "job_queue_full": 429,
        "job_not_found": 404,
        "job_already_running": 409,
        "upstream_dirty": 409,
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
        "short_edit_failed": 422,
        "tts_failed": 502,
        "llm_failed": 502,
        "transcript_not_found": 404,
        "transcript_required": 422,
        "invalid_override": 422,
        "word_overrides_not_supported": 422,
        "invalid_time": 422,
        "invalid_config": 422,
        "recipe_invalid": 422,
        "step_failed": 422,
        "batch_invalid": 422,
        "export_failed": 422,
        "ingest_failed": 422,
        "not_implemented": 501,
    }.get(code, 400)
