"""Markdown style catalog routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from videoflow.application import style_service
from videoflow.domain.errors import VideoFlowError
from videoflow.domain.paths import resolve_allowed
from videoflow.runtime import allowed_roots


class StyleSaveRequest(BaseModel):
    style_id: str = ""
    name: str = ""
    markdown_content: str = ""
    aspect_ratio: str | None = None
    target_lufs: float | None = None
    max_static_sec: float | None = None
    min_silence_ms: int | None = None
    layout_mode: str | None = None
    caption_preset: str | None = None
    motion_engine: str | None = None
    platforms: list[str] | None = None
    beatmap_defaults: dict[str, Any] | None = None
    sound_design: dict[str, Any] | None = None
    hook_strategy: str | None = None
    intro_strategy: str | None = None
    export_targets: list[str] | None = None
    palette: list[str] | None = None
    fonts: list[str] | None = None
    cut_rhythm: dict[str, Any] | None = None
    safe_zones: dict[str, Any] | None = None
    body: str | None = None
    workspace_dir: str = ""
    overwrite: bool = True


class StyleLearnRequest(BaseModel):
    notes: list[str] = Field(default_factory=list)
    mode: str = "merge"
    max_rules: int = Field(default=15, ge=1, le=15)
    workspace_dir: str = ""


class StyleSyncRequest(BaseModel):
    workspace_dir: str = Field(min_length=1)
    overwrite: bool = False


def _workspace(value: str) -> str | None:
    if not value.strip():
        return None
    return str(resolve_allowed(Path(value), allowed_roots()))


def _updates(request: StyleSaveRequest) -> dict[str, Any]:
    return {
        key: value
        for key, value in (
            ("body", request.body),
            ("aspect_ratio", request.aspect_ratio),
            ("target_lufs", request.target_lufs),
            ("max_static_sec", request.max_static_sec),
            ("min_silence_ms", request.min_silence_ms),
            ("layout_mode", request.layout_mode),
            ("caption_preset", request.caption_preset),
            ("motion_engine", request.motion_engine),
            ("platforms", request.platforms),
            ("beatmap_defaults", request.beatmap_defaults),
            ("sound_design", request.sound_design),
            ("hook_strategy", request.hook_strategy),
            ("intro_strategy", request.intro_strategy),
            ("export_targets", request.export_targets),
            ("palette", request.palette),
            ("fonts", request.fonts),
            ("cut_rhythm", request.cut_rhythm),
            ("safe_zones", request.safe_zones),
        )
        if value is not None
    }


def register_style_routes(app: FastAPI) -> None:
    """Register style catalog routes."""

    @app.get("/api/v1/styles")
    def styles_list() -> dict[str, object]:
        return {"ok": True, "styles": style_service.list_styles()}

    @app.get("/api/v1/styles/{style_id}")
    def styles_get(style_id: str) -> dict[str, object]:
        try:
            return style_service.get_style(style_id)
        except VideoFlowError as exc:
            return exc.to_dict()

    @app.post("/api/v1/styles", status_code=201)
    def styles_save(request: StyleSaveRequest) -> dict[str, object]:
        try:
            return style_service.save_style(
                style_id=request.style_id,
                name=request.name,
                markdown_content=request.markdown_content,
                updates=_updates(request),
                overwrite=request.overwrite,
                workspace_dir=_workspace(request.workspace_dir),
            )
        except (VideoFlowError, ValueError) as exc:
            if isinstance(exc, VideoFlowError):
                return exc.to_dict()
            return {"ok": False, "code": "invalid_style", "message": str(exc)}

    @app.delete("/api/v1/styles/{style_id}")
    def styles_delete(style_id: str) -> dict[str, object]:
        return style_service.delete_style(style_id)

    @app.post("/api/v1/styles/{style_id}/learn")
    def styles_learn(style_id: str, request: StyleLearnRequest) -> dict[str, object]:
        try:
            return style_service.learn_style(
                style_id,
                request.notes,
                mode=request.mode,
                max_rules=request.max_rules,
                workspace_dir=_workspace(request.workspace_dir),
            )
        except VideoFlowError as exc:
            return exc.to_dict()

    @app.post("/api/v1/styles/sync")
    def styles_sync(request: StyleSyncRequest) -> dict[str, object]:
        try:
            return style_service.sync_styles(
                _workspace(request.workspace_dir) or "",
                overwrite=request.overwrite,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
