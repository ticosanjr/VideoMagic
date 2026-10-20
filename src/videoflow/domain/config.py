"""Rack configuration. Defaults are CPU-first. Secrets are names, never values."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from videoflow.domain.constants import DEFAULT_SECRET_NAME, PROMPT_TEMPLATE_VERSION

ModelSize = Literal["tiny", "base", "small", "medium", "large-v3"]
MediaLanguage = Literal["pt", "it", "en", "es", "auto"]
ComputeDevice = Literal["cuda", "cpu"]
ComputeType = Literal["float16", "int8", "float32"]
VadEngine = Literal["auto", "silero", "ffmpeg"]
WhisperEngine = Literal["auto", "faster-whisper", "whisper.cpp"]
LlmProvider = Literal["ollama", "openai_compatible"]
Strictness = Literal["conservative", "balanced", "aggressive"]
RetakeStrategy = Literal["keep_last", "keep_best"]
ZoomMode = Literal["alternate_cuts", "topic_change", "manual_rules"]
AnchorPoint = Literal["center", "upper_third", "face_detect"]
PanDirection = Literal["none", "left_to_right", "right_to_left"]
ReframeMode = Literal["center_crop_9_16", "auto_face_tracking_yolo"]
SubtitlePreset = Literal["tiktok_bold", "minimalist_box", "highlight_word"]
ShortsExportFormat = Literal["fcpxml_timeline", "standalone_mp4", "both"]
FcpxmlDialect = Literal["1.9", "1.10"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IngestConfig(StrictModel):
    force_cfr: bool = True
    extract_audio_pcm: bool = True
    generate_proxy: bool = False


class VadConfig(StrictModel):
    engine: VadEngine = "auto"
    speech_threshold: float = Field(default=0.5, ge=0.1, le=0.9)
    min_silence_duration_ms: int = Field(default=400, ge=0)
    speech_pad_before_ms: int = Field(default=120, ge=0)
    speech_pad_after_ms: int = Field(default=150, ge=0)
    keep_handles_ms: int = Field(default=200, ge=0)


class TranscribeConfig(StrictModel):
    engine: WhisperEngine = "auto"
    model_size: ModelSize = "small"
    language: MediaLanguage = "pt"
    device: ComputeDevice = "cpu"
    compute_type: ComputeType = "int8"
    vad_filter: bool = False


class RetakesConfig(StrictModel):
    provider: LlmProvider = "ollama"
    base_url: str = "http://localhost:11434/v1"
    secret_name: str = DEFAULT_SECRET_NAME
    model_name: str = "qwen2.5:7b-instruct"
    strictness: Strictness = "balanced"
    context_window_sentences: int = Field(default=15, ge=1, le=100)
    retake_strategy: RetakeStrategy = "keep_last"
    temperature: float = Field(default=0.0, ge=0.0, le=0.0)
    prompt_template_version: str = PROMPT_TEMPLATE_VERSION


class JlCutsConfig(StrictModel):
    enable_j_cuts: bool = True
    enable_l_cuts: bool = False
    offset_ms: int = Field(default=200, ge=100, le=500)
    audio_crossfade_ms: int = Field(default=20, ge=10, le=50)
    handle_check: bool = True


class ZoomsConfig(StrictModel):
    mode: ZoomMode = "alternate_cuts"
    punch_in_scale: float = Field(default=1.15, ge=1.05, le=1.30)
    anchor_point: AnchorPoint = "upper_third"
    progressive_zoom: bool = False
    pan_direction: PanDirection = "none"


class ShortsConfig(StrictModel):
    target_duration_min_sec: int = Field(default=30, ge=1)
    target_duration_max_sec: int = Field(default=60, ge=1)
    max_clips_to_generate: int = Field(default=3, ge=1, le=20)
    reframe_mode: ReframeMode = "center_crop_9_16"
    burn_subtitles: bool = True
    subtitles_preset: SubtitlePreset = "tiktok_bold"
    export_format: ShortsExportFormat = "both"

    @model_validator(mode="after")
    def duration_window(self) -> Self:
        if self.target_duration_min_sec > self.target_duration_max_sec:
            raise ValueError("target_duration_min_sec exceeds target_duration_max_sec")
        return self


class ExportConfig(StrictModel):
    fcpxml_dialect: FcpxmlDialect = "1.9"
    write_fcpxml: bool = True
    write_xmeml: bool = True
    write_otio: bool = True
    write_mp4: bool = False


class ModulesConfig(StrictModel):
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    vad: VadConfig = Field(default_factory=VadConfig)
    transcribe: TranscribeConfig = Field(default_factory=TranscribeConfig)
    retakes: RetakesConfig = Field(default_factory=RetakesConfig)
    jl_cuts: JlCutsConfig = Field(default_factory=JlCutsConfig)
    zooms: ZoomsConfig = Field(default_factory=ZoomsConfig)
    shorts: ShortsConfig = Field(default_factory=ShortsConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)


class ModuleEnabled(StrictModel):
    ingest: bool = True
    vad: bool = True
    transcribe: bool = True
    retakes: bool = True
    jl_cuts: bool = True
    zooms: bool = True
    shorts: bool = True
    export: bool = True

    def as_map(self) -> dict[str, bool]:
        return self.model_dump()
