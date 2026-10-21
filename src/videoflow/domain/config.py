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
ShortsSelectionMode = Literal["auto", "llm", "heuristic"]
ShortsAspect = Literal["9:16", "1:1", "16:9"]
ShortsPromptMode = Literal["replace", "refine"]
ShortsHookMode = Literal["off", "metadata", "repeat", "reorder"]
CaptionAnimation = Literal["none", "pop", "sweep"]
CaptionWordTiming = Literal["engine", "proportional", "sentence"]
FadeCurve = Literal["linear", "logarithmic"]
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
    fade_in_ms: int = Field(default=20, ge=0, le=1000)
    fade_out_ms: int = Field(default=20, ge=0, le=1000)
    fade_curve: FadeCurve = "logarithmic"
    handle_check: bool = True


class ZoomsConfig(StrictModel):
    mode: ZoomMode = "alternate_cuts"
    min_scale: float = Field(default=1.0, ge=1.0, le=4.0)
    max_scale: float = Field(default=1.5, ge=1.0, le=4.0)
    punch_in_scale: float = Field(default=1.15, ge=1.0, le=4.0)
    anchor_point: AnchorPoint = "upper_third"
    progressive_zoom: bool = False
    pan_direction: PanDirection = "none"

    @model_validator(mode="after")
    def scale_window(self) -> Self:
        if self.min_scale > self.max_scale:
            raise ValueError("min_scale exceeds max_scale")
        if not self.min_scale <= self.punch_in_scale <= self.max_scale:
            raise ValueError("punch_in_scale must be inside min_scale and max_scale")
        return self


class CaptionStyle(StrictModel):
    """Burned caption/karaoke style. Colors are #RRGGBB."""

    font_family: str = Field(default="Arial", min_length=1)
    font_size: int = Field(default=72, ge=8, le=300)
    font_weight: Literal["normal", "bold"] = "bold"
    italic: bool = False
    uppercase: bool = False
    primary_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    highlight_color: str = Field(default="#FFD400", pattern=r"^#[0-9A-Fa-f]{6}$")
    outline_color: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    outline_width: int = Field(default=4, ge=0, le=20)
    shadow_color: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    shadow_offset: int = Field(default=2, ge=0, le=20)
    shadow_opacity: float = Field(default=0.6, ge=0.0, le=1.0)
    background_color: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    background_opacity: float = Field(default=0.0, ge=0.0, le=1.0)
    background_padding: int = Field(default=0, ge=0, le=40)
    alignment: int = Field(default=2, ge=1, le=9)
    position_x: float = Field(default=0.5, ge=0.0, le=1.0)
    position_y: float = Field(default=0.78, ge=0.0, le=1.0)
    max_width: float = Field(default=0.9, ge=0.2, le=1.0)
    animation: CaptionAnimation = "none"
    word_timing: CaptionWordTiming = "engine"


class ShortsConfig(StrictModel):
    target_duration_min_sec: int = Field(default=30, ge=1)
    target_duration_max_sec: int = Field(default=60, ge=1)
    min_clips: int = Field(default=3, ge=1, le=20)
    max_clips_to_generate: int = Field(default=3, ge=1, le=20)
    selection_mode: ShortsSelectionMode = "auto"
    prompt: str = Field(default="", max_length=2000)
    reprompt: str = Field(default="", max_length=2000)
    prompt_mode: ShortsPromptMode = "replace"
    hook_mode: ShortsHookMode = "off"
    reframe_mode: ReframeMode = "center_crop_9_16"
    aspect_ratio: ShortsAspect = "9:16"
    source_start_sec: float = Field(default=0.0, ge=0.0)
    source_end_sec: float | None = Field(default=None, ge=0.0)
    burn_subtitles: bool = True
    subtitles_preset: SubtitlePreset = "tiktok_bold"
    caption_style: CaptionStyle = Field(default_factory=CaptionStyle)
    export_format: ShortsExportFormat = "both"

    @model_validator(mode="after")
    def duration_window(self) -> Self:
        if self.target_duration_min_sec > self.target_duration_max_sec:
            raise ValueError("target_duration_min_sec exceeds target_duration_max_sec")
        if self.min_clips > self.max_clips_to_generate:
            raise ValueError("min_clips exceeds max_clips_to_generate")
        if self.source_end_sec is not None and self.source_end_sec <= self.source_start_sec:
            raise ValueError("source_end_sec must be greater than source_start_sec")
        return self


class ExportConfig(StrictModel):
    fcpxml_dialect: FcpxmlDialect = "1.9"
    write_fcpxml: bool = True
    write_xmeml: bool = True
    write_otio: bool = True
    write_mp4: bool = False


class ProvidersConfig(StrictModel):
    allow_external_services: bool = False
    allowed_hosts: list[str] = Field(default_factory=list)


class ModulesConfig(StrictModel):
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
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
