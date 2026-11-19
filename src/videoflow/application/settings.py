"""Local-first application settings with atomic JSON persistence."""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from videoflow.application.schema_migrations import migrate_settings
from videoflow.runtime import portable_home

SETTINGS_FILE = "settings.json"
logger = logging.getLogger(__name__)
_error_lock = threading.Lock()
_last_error = ""


def settings_error() -> str:
    with _error_lock:
        return _last_error


def _set_error(message: str) -> None:
    global _last_error
    with _error_lock:
        _last_error = message
    if message:
        logger.warning("%s", message)


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    open_browser: bool = True
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    max_jobs: int = Field(default=2, ge=1, le=16)
    history: int = Field(default=50, ge=5, le=500)
    locale: str = "en"


class PathSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_roots: list[str] = Field(default_factory=list)
    ffmpeg: str = ""
    ffprobe: str = ""
    cache_dir: str = ""
    models_dir: str = ""
    output_root: str = ""
    temp_dir: str = ""


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defaults: dict[str, str] = Field(default_factory=dict)
    device: Literal["cpu", "cuda", "auto"] = "cpu"
    compute_type: str = "int8"
    threads: int = Field(default=0, ge=0, le=128)
    hf_token_env: str = "HF_TOKEN"


class AutomationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheduler_interval_seconds: int = Field(default=20, ge=5, le=3600)
    max_retries: int = Field(default=5, ge=0, le=20)
    retry_backoff_seconds: int = Field(default=30, ge=5, le=3600)
    enabled: bool = True


class QualitySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_lufs: float = Field(default=-16.0, ge=-30.0, le=-5.0)
    true_peak_db: float = Field(default=-1.0, ge=-20.0, le=0.0)
    vmaf_threshold: float = Field(default=90.0, ge=0.0, le=100.0)
    proxy_height: int = Field(default=540, ge=144, le=1080)


class UiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: Literal["dark", "light", "system", "high-contrast"] = "dark"
    density: Literal["comfortable", "compact"] = "comfortable"
    timeline_snap: bool = True


class LlmSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    timeout_seconds: float = Field(default=90.0, ge=5.0, le=600.0)
    max_tokens: int = Field(default=0, ge=0, le=200000)
    retries: int = Field(default=2, ge=0, le=10)
    json_mode: bool = True


class SpeechSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: Literal["auto", "faster-whisper", "whisper-cli"] = "auto"
    quality_profile: Literal[
        "auto", "custom", "fast", "balanced", "quality", "vulkan", "remote"
    ] = "balanced"
    language: str = "pt"
    device: Literal["cpu", "cuda", "auto"] = "cpu"
    compute_type: str = "int8"
    beam_size: int = Field(default=1, ge=1, le=10)
    cpu_threads: int = Field(default=0, ge=0, le=128)
    word_timestamps: Literal["auto", "always", "off"] = "auto"
    condition_on_previous_text: bool = False
    vad_filter: bool = False
    remote_base_url: str = ""
    remote_model: str = "whisper-1"
    remote_api_key_env: str = "VIDEOWFLOW_ASR_API_KEY"
    diarization_model: str = "pyannote-diarization-3.1"
    offset_mode: Literal["off", "auto", "fixed"] = "off"
    offset_ms: int = Field(default=0, ge=-2000, le=2000)
    drift_threshold_ms: int = Field(default=40, ge=1, le=2000)


class TtsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["openai_compatible", "piper"] = "openai_compatible"
    voice: str = "alloy"
    model: str = "tts-1"
    format: Literal["mp3", "wav"] = "mp3"
    speed: float = Field(default=1.0, ge=0.25, le=4.0)


class StockSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["local", "pexels"] = "local"
    pexels_key_env: str = "PEXELS_API_KEY"
    pixabay_key_env: str = "PIXABAY_API_KEY"
    openverse_token_env: str = "OPENVERSE_TOKEN"
    asset_dir: str = ""
    youtube_fair_use_seconds: int = Field(default=15, ge=1, le=120)
    youtube_max_per_video: int = Field(default=3, ge=1, le=10)
    allow_fair_use: bool = True


class TranslationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_language: str = "en"
    source_language: str = "auto"


class LocalNotificationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    desktop: bool = False


class EmailNotificationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    smtp_user: str = ""
    smtp_password_secret: str = "VIDEOWFLOW_SMTP_PASSWORD"
    from_address: str = ""
    to_addresses: list[str] = Field(default_factory=list)
    imap_host: str = ""
    imap_port: int = Field(default=993, ge=1, le=65535)
    imap_ssl: bool = True
    imap_user: str = ""
    imap_password_secret: str = "VIDEOWFLOW_IMAP_PASSWORD"
    imap_folder: str = "INBOX"
    allowed_senders: list[str] = Field(default_factory=list)
    poll_seconds: int = Field(default=30, ge=10, le=3600)
    max_attachment_mb: int = Field(default=512, ge=1, le=8192)


class SlackNotificationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    mode: Literal["webhook", "bot"] = "webhook"
    webhook_secret: str = "VIDEOWFLOW_SLACK_WEBHOOK_URL"
    bot_token_secret: str = "VIDEOWFLOW_SLACK_BOT_TOKEN"
    signing_secret: str = "VIDEOWFLOW_SLACK_SIGNING_SECRET"
    channel: str = ""
    allowed_users: list[str] = Field(default_factory=list)
    poll_seconds: int = Field(default=30, ge=10, le=3600)
    use_events: bool = False


class SignalNotificationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    api_url: str = "http://127.0.0.1:8080"
    number: str = ""
    recipients: list[str] = Field(default_factory=list)
    allowed_senders: list[str] = Field(default_factory=list)
    password_secret: str = "VIDEOWFLOW_SIGNAL_PASSWORD"
    poll_seconds: int = Field(default=30, ge=10, le=3600)


class NotificationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    default_channels: list[str] = Field(default_factory=list)
    base_url: str = "http://127.0.0.1:8765"
    interaction_ttl_hours: int = Field(default=168, ge=1, le=24 * 365)
    reminder_hours: int = Field(default=24, ge=1, le=24 * 365)
    ui_level: Literal["off", "required", "important", "all"] = "off"
    desktop_level: Literal["off", "required", "important", "all"] = "off"
    notify_hitl: bool = True
    notify_job_failed: bool = True
    notify_job_finished: bool = False
    notify_job_cancelled: bool = False
    notify_warnings: bool = False
    notify_system: bool = False
    local: LocalNotificationSettings = Field(default_factory=LocalNotificationSettings)
    email: EmailNotificationSettings = Field(default_factory=EmailNotificationSettings)
    slack: SlackNotificationSettings = Field(default_factory=SlackNotificationSettings)
    signal: SignalNotificationSettings = Field(default_factory=SignalNotificationSettings)

    @field_validator("ui_level", "desktop_level", mode="before")
    @classmethod
    def _legacy_level(cls, value: object) -> object:
        """Map the pre-2.72.2 levels onto the reduced notification levels."""

        if isinstance(value, str):
            aliases = {
                "minimal": "required",
                "standard": "important",
                "verbose": "all",
            }
            return aliases.get(value.strip().lower(), value)
        return value


class SearchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    providers: list[str] = Field(default_factory=lambda: ["local"])
    local_paths: list[str] = Field(default_factory=list)
    seed_urls: list[str] = Field(default_factory=list)
    searxng_url: str = ""
    wikipedia_language: str = "pt"
    max_results: int = Field(default=6, ge=1, le=50)
    fetch_pages: int = Field(default=3, ge=0, le=20)
    allow_network: bool = False
    timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    max_bytes: int = Field(default=2_000_000, ge=10_000, le=50_000_000)
    cache_ttl_hours: int = Field(default=24, ge=1, le=24 * 30)


class TaskPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_order: list[str] = Field(default_factory=list)
    model: str = ""
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=0, ge=0, le=200000)
    timeout_seconds: float = Field(default=120.0, ge=5.0, le=600.0)
    fallback: Literal["deterministic", "error", "none"] = "deterministic"
    enabled: bool = True


class IntelligenceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    provider_order: list[str] = Field(
        default_factory=lambda: ["opencode_v2", "deepseek", "openai_compatible"]
    )
    allow_network: bool = False
    budget_usd: float = Field(default=0.0, ge=0.0)
    cache_enabled: bool = True
    default_timeout_seconds: float = Field(default=120.0, ge=5.0, le=600.0)
    opencode_base_url: str = ""
    opencode_token_env: str = "OPENCODE_TOKEN"
    opencode_model: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_api_key_env: str = "DEEPSEEK_API_KEY"
    tasks: dict[str, TaskPolicy] = Field(default_factory=dict)


class HeadlessSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mcp_only: bool = False
    start_ui: bool = True
    start_tray: bool = True
    start_hilt_pollers: bool = True


class SyncSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offset_mode: Literal["off", "auto", "fixed"] = "off"
    offset_ms: int = Field(default=0, ge=-2000, le=2000)
    drift_threshold_ms: int = Field(default=40, ge=1, le=2000)
    reference_audio: str = ""


class RenderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    serialized: bool = True
    draft_scale: float = Field(default=0.5, ge=0.1, le=1.0)
    motion_blur: bool = True
    max_concurrent_heavy: int = Field(default=1, ge=1, le=4)


class QaSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visual_fps: int = Field(default=10, ge=1, le=30)
    window_pad_sec: float = Field(default=0.5, ge=0.0, le=5.0)
    fail_on_defects: bool = False
    backends: list[str] = Field(default_factory=lambda: ["deterministic"])


class VisionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracking_backend: Literal["auto", "mediapipe", "yolo", "opencv_haar", "motion_tracking"] = (
        "auto"
    )
    yolo_model: str = ""
    yolo_confidence: float = Field(default=0.35, ge=0.0, le=1.0)
    mediapipe_model: int = Field(default=1, ge=0, le=1)
    mediapipe_model_path: str = ""
    tracking_smoothing: float = Field(default=0.85, ge=0.0, le=0.99)
    tracking_sample_fps: int = Field(default=2, ge=1, le=30)


class WebRenderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: Literal["auto", "html", "hyperframes", "remotion"] = "auto"
    browser: Literal["chrome", "chromium"] = "chrome"
    allow_network: bool = False
    timeout_seconds: int = Field(default=120, ge=5, le=1800)


class PresetSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel_dir: str = ""
    style_dir: str = ""
    workflow_dir: str = ""
    max_rules: int = Field(default=200, ge=1, le=2000)


class GpuSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["auto", "local_only", "remote_preferred"] = "auto"
    worker_url: str = ""
    worker_id: str = ""
    worker_token_secret: str = "VF_GPU_WORKER_TOKEN"
    capabilities: dict[str, bool] = Field(
        default_factory=lambda: {
            "asr": True,
            "render_nvenc": True,
            "segment_matte": True,
            "face_track": True,
            "stems": False,
            "upscale": True,
            "tts": False,
            "comfyui": False,
        }
    )
    shared_mount_enabled: bool = False
    shared_linux_path: str = ""
    shared_windows_path: str = ""
    max_vram_mb: int = Field(default=10_240, ge=4096, le=24_576)
    model_unload_ttl_sec: int = Field(default=300, ge=30, le=86_400)
    fallback_local: bool = True
    discovery_enabled: bool = True


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    paths: PathSettings = Field(default_factory=PathSettings)
    models: ModelSettings = Field(default_factory=ModelSettings)
    automation: AutomationSettings = Field(default_factory=AutomationSettings)
    quality: QualitySettings = Field(default_factory=QualitySettings)
    ui: UiSettings = Field(default_factory=UiSettings)
    llm: LlmSettings = Field(default_factory=LlmSettings)
    speech: SpeechSettings = Field(default_factory=SpeechSettings)
    tts: TtsSettings = Field(default_factory=TtsSettings)
    stock: StockSettings = Field(default_factory=StockSettings)
    translation: TranslationSettings = Field(default_factory=TranslationSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    intelligence: IntelligenceSettings = Field(default_factory=IntelligenceSettings)
    headless: HeadlessSettings = Field(default_factory=HeadlessSettings)
    sync: SyncSettings = Field(default_factory=SyncSettings)
    render: RenderSettings = Field(default_factory=RenderSettings)
    qa: QaSettings = Field(default_factory=QaSettings)
    vision: VisionSettings = Field(default_factory=VisionSettings)
    web_render: WebRenderSettings = Field(default_factory=WebRenderSettings)
    presets: PresetSettings = Field(default_factory=PresetSettings)
    gpu: GpuSettings = Field(default_factory=GpuSettings)


def settings_path() -> Path:
    return portable_home() / SETTINGS_FILE


def load_settings() -> AppSettings:
    path = settings_path()
    if not path.is_file():
        _set_error("")
        return AppSettings()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        settings = AppSettings.model_validate(migrate_settings(payload))
    except (OSError, ValueError, TypeError) as exc:
        _set_error(f"settings.json is invalid; using defaults: {exc}")
        return AppSettings()
    _set_error("")
    return settings


def save_settings(settings: AppSettings) -> AppSettings:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(settings.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temp.replace(path)
    return settings


def effective_roots(settings: AppSettings | None = None) -> list[str]:
    raw = os.environ.get("VIDEOWFLOW_ALLOWED_ROOTS", "")
    if raw:
        return [item for item in raw.split(os.pathsep) if item]
    current = settings or load_settings()
    if current.paths.allowed_roots:
        return [str(Path(item).expanduser()) for item in current.paths.allowed_roots]
    return []


def effective_ffmpeg(name: str, settings: AppSettings | None = None) -> str:
    current = settings or load_settings()
    configured = current.paths.ffmpeg if name == "ffmpeg" else current.paths.ffprobe
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return str(path)
    return ""


def env_overrides() -> dict[str, str]:
    keys = (
        "VIDEOWFLOW_HOME",
        "VIDEOWFLOW_ALLOWED_ROOTS",
        "VIDEOWFLOW_ALLOW_EXTERNAL",
        "VIDEOWFLOW_LLM_BASE_URL",
        "VIDEOWFLOW_LLM_MODEL",
        "VIDEOWFLOW_OPENCODE_BASE_URL",
        "VIDEOWFLOW_OPENCODE_MODEL",
        "VIDEOWFLOW_DEEPSEEK_API_KEY",
        "VIDEOWFLOW_COST_BUDGET_USD",
        "VIDEOWFLOW_ASR_BASE_URL",
        "VIDEOWFLOW_ASR_MODEL",
        "VIDEOWFLOW_VISION_BASE_URL",
        "VIDEOWFLOW_VISION_MODEL",
        "VIDEOWFLOW_WHISPER_BIN",
        "VIDEOWFLOW_WHISPER_MODEL",
        "VIDEOWFLOW_FASTER_WHISPER_MODEL",
        "VIDEOWFLOW_SILERO_MODEL",
        "HF_TOKEN",
        "PEXELS_API_KEY",
        "VIDEOWFLOW_RECIPE_SCHEDULER",
    )
    return {key: os.environ[key] for key in keys if os.environ.get(key)}
