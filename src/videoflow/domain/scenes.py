"""Scene-intelligence contracts for the Shorts compositor."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SceneLayout = Literal[
    "TALKING_HEAD",
    "SCREEN_SHARE_PIP",
    "SCREEN_SHARE_FULL",
    "DUAL_CANVAS_OBS",
    "BROLL_OR_FOOTAGE",
]
SourceTopology = Literal["single_16x9", "dual_canvas", "dual_file"]
TransitionSource = Literal["VISUAL_CUT", "DECUPAGEM_JUMP"]


class SceneFaceBox(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cx: float = Field(ge=0.0, le=1.0)
    cy: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)


class SceneEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(pattern=r"^SC_\d+$")
    start_sample: int = Field(ge=0)
    end_sample: int = Field(gt=0)
    start_sec: float = Field(ge=0.0)
    end_sec: float = Field(gt=0.0)
    transition_source: TransitionSource = "VISUAL_CUT"
    layout_type: SceneLayout
    face_count: int = Field(default=0, ge=0)
    face_bbox_norm: SceneFaceBox | None = None
    face_area_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    edge_density: float = Field(default=0.0, ge=0.0, le=1.0)
    sharpness_laplacian: float = Field(default=0.0, ge=0.0)
    keyframe_path: str = ""
    editing_hints: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_span(self) -> SceneEntry:
        if self.end_sample <= self.start_sample:
            raise ValueError("scene end_sample must be after start_sample")
        if self.end_sec <= self.start_sec:
            raise ValueError("scene end_sec must be after start_sec")
        return self


class ScenesManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    video_id: str = Field(min_length=1)
    source_topology: SourceTopology = "single_16x9"
    resolution: dict[str, int]
    fps_num: int = Field(gt=0)
    fps_den: int = Field(gt=0)
    scenes: list[SceneEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_scene_ids(self) -> ScenesManifest:
        ids = [scene.scene_id for scene in self.scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("scene ids must be unique")
        return self
