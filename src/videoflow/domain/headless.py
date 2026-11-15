"""Serializable models for the headless/MCP edition."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class HeadlessModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BeatScene(HeadlessModel):
    id: str
    start_sec: float = Field(ge=0.0)
    end_sec: float = Field(ge=0.0)
    script: str = ""
    visual: str = ""
    archetype: str = "talking_head"
    web_scene: str = ""
    audio_cue: str = ""
    assets: list[str] = Field(default_factory=list)
    qa_windows: list[tuple[float, float]] = Field(default_factory=list)


class BeatTrack(HeadlessModel):
    id: str
    kind: Literal["voice", "music", "sfx", "video"] = "voice"
    path: str = ""
    gain_db: float = 0.0
    start_sec: float = 0.0
    end_sec: float = 0.0


class BeatMap(HeadlessModel):
    schema_version: int = 1
    project_id: str = ""
    fps_num: int = 30000
    fps_den: int = 1001
    duration_sec: float = 0.0
    scenes: list[BeatScene] = Field(default_factory=list)
    tracks: list[BeatTrack] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Archetype(HeadlessModel):
    id: str
    label: str = ""
    kind: Literal["talking_head", "cutout", "motion_full", "split_screen", "broll", "custom"] = (
        "talking_head"
    )
    scene_ids: list[str] = Field(default_factory=list)
    duration_sec: float = 0.0
    preview_path: str = ""


class VisualQaDefect(HeadlessModel):
    kind: str
    start_sec: float = 0.0
    end_sec: float = 0.0
    confidence: float = 0.0
    message: str = ""
    frame_paths: list[str] = Field(default_factory=list)
    bbox: list[float] = Field(default_factory=list)
    severity: Literal["info", "warning", "error"] = "warning"


class VisualQaReport(HeadlessModel):
    schema_version: int = 1
    job_id: str = ""
    fps: int = 10
    window_pad_sec: float = 0.5
    checked_windows: int = 0
    defects: list[VisualQaDefect] = Field(default_factory=list)
    frames_dir: str = ""
    passed: bool = True


class SafeZoneBox(HeadlessModel):
    platform: str
    x: float
    y: float
    width: float
    height: float
    reason: str = ""


class SafeZoneCollision(HeadlessModel):
    platform: str
    element_id: str = ""
    element_kind: str = ""
    start_sec: float = 0.0
    end_sec: float = 0.0
    bbox: list[float] = Field(default_factory=list)
    safe_zone: SafeZoneBox | None = None
    message: str = ""


class SafeZoneReport(HeadlessModel):
    schema_version: int = 1
    platforms: list[str] = Field(default_factory=list)
    collisions: list[SafeZoneCollision] = Field(default_factory=list)
    passed: bool = True


class PacingCue(HeadlessModel):
    start_sec: float
    end_sec: float
    action: Literal["zoom", "layout", "broll", "none"] = "zoom"
    reason: str = ""


class GazeSpan(HeadlessModel):
    start_sec: float
    end_sec: float
    state: Literal["camera", "teleprompter", "unknown"] = "unknown"
    confidence: float = 0.0


class CapturedAsset(HeadlessModel):
    kind: Literal["screenshot", "clip"] = "screenshot"
    url: str = ""
    path: str = ""
    start_sec: float = 0.0
    end_sec: float = 0.0
    width: int = 0
    height: int = 0
    license: str = ""
    source: str = ""


class ReferenceBoard(HeadlessModel):
    path: str = ""
    entities: list[str] = Field(default_factory=list)
    units: list[str] = Field(default_factory=list)
    entries: list[dict[str, Any]] = Field(default_factory=list)


class TransformativeRecord(HeadlessModel):
    source: str
    output: str
    mode: str
    zoom: float = 1.0
    crop: list[float] = Field(default_factory=list)
    overlay: str = ""
    note: str = ""


class SfxCue(HeadlessModel):
    kind: Literal["whoosh", "click", "riser", "foley"] = "whoosh"
    start_sec: float = 0.0
    duration_sec: float = 0.25
    gain_db: float = -6.0
    path: str = ""
    sync_to: str = ""


class PresetRule(HeadlessModel):
    id: str
    text: str
    scope: str = "global"
    weight: float = 1.0
    source: str = ""
    created_at: str = ""


class PresetRulebook(HeadlessModel):
    schema_version: int = 1
    channel_id: str = ""
    version: int = 1
    rules: list[PresetRule] = Field(default_factory=list)


class StylePreset(HeadlessModel):
    schema_version: int = 1
    name: str = ""
    palette: list[str] = Field(default_factory=list)
    typography: dict[str, Any] = Field(default_factory=dict)
    cut_rhythm: dict[str, Any] = Field(default_factory=dict)
    safe_zones: dict[str, Any] = Field(default_factory=dict)
    source: str = ""


class NleSyncReport(HeadlessModel):
    format: str
    applied: bool = False
    changed_clips: int = 0
    conflicts: list[str] = Field(default_factory=list)
    transcript_updates: int = 0
    broll_updates: int = 0
    warnings: list[str] = Field(default_factory=list)


class IntroPlan(HeadlessModel):
    max_sec: float = 120.0
    sources: list[str] = Field(default_factory=list)
    sfx: list[str] = Field(default_factory=list)
    segments: list[dict[str, Any]] = Field(default_factory=list)


class SyncReport(HeadlessModel):
    offset_ms: int = 0
    drift_ms: int = 0
    applied: bool = False
    mode: str = "off"
    reason: str = ""
    sources: list[str] = Field(default_factory=list)


class SelfHealReport(HeadlessModel):
    step: str
    attempt: int = 1
    max_attempts: int = 3
    code: str = "step_failed"
    message: str = ""
    command: str = ""
    stderr: str = ""
    returncode: int | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    partial_artifacts: list[str] = Field(default_factory=list)
