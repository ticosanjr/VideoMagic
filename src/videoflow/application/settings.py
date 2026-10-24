"""Local-first application settings with atomic JSON persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.schema_migrations import migrate_settings
from videoflow.runtime import portable_home

SETTINGS_FILE = "settings.json"


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
    language: str = "pt"
    device: Literal["cpu", "cuda", "auto"] = "cpu"
    compute_type: str = "int8"
    vad_filter: bool = False
    diarization_model: str = "pyannote-diarization-3.1"


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
    asset_dir: str = ""


class TranslationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_language: str = "en"
    source_language: str = "auto"


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


def settings_path() -> Path:
    return portable_home() / SETTINGS_FILE


def load_settings() -> AppSettings:
    path = settings_path()
    if not path.is_file():
        return AppSettings()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return AppSettings.model_validate(migrate_settings(payload))
    except (OSError, ValueError, TypeError):
        return AppSettings()


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
