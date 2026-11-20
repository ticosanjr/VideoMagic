"""Format preset CRUD routes."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from videoflow.application.format_catalog import FormatCatalog
from videoflow.domain.errors import VideoFlowError
from videoflow.domain.formats import AspectRatio


class FormatSaveRequest(BaseModel):
    format_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    aspect_ratio: AspectRatio = "9:16"
    width: int = 1080
    height: int = 1920
    fps: int = 30
    safe_zones: dict[str, float] = Field(default_factory=dict)
    caption_preset: str = "youtube_bold_yellow"
    platforms: list[str] = Field(default_factory=list)
    export_targets: list[str] = Field(default_factory=list)
    description: str = ""


class FormatDuplicateRequest(BaseModel):
    new_id: str = ""
    name: str = ""


def register_format_routes(app: FastAPI) -> None:
    @app.get("/api/v1/formats")
    def list_formats() -> dict[str, object]:
        return {"ok": True, "formats": FormatCatalog().list_payload()}

    @app.get("/api/v1/formats/{format_id}")
    def get_format(format_id: str) -> dict[str, object]:
        try:
            item = FormatCatalog().get(format_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        return {"ok": True, "format": item.model_dump(mode="json")}

    @app.post("/api/v1/formats")
    def save_format(payload: FormatSaveRequest) -> dict[str, object]:
        from videoflow.domain.formats import FormatDefinition

        try:
            definition = FormatDefinition.model_validate(payload.model_dump())
            path = FormatCatalog().save(definition)
        except (VideoFlowError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail={"ok": False, "code": "invalid_format", "message": str(exc)},
            ) from exc
        return {"ok": True, "format": definition.model_dump(mode="json"), "file": str(path)}

    @app.delete("/api/v1/formats/{format_id}")
    def delete_format(format_id: str) -> dict[str, object]:
        try:
            deleted = FormatCatalog().delete(format_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
        return {"ok": True, "deleted": deleted}

    @app.post("/api/v1/formats/{format_id}/duplicate")
    def duplicate_format(format_id: str, payload: FormatDuplicateRequest) -> dict[str, object]:
        try:
            item = FormatCatalog().duplicate(
                format_id,
                payload.new_id or f"{format_id}-copy",
                name=payload.name,
            )
        except (VideoFlowError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail={"ok": False, "code": "invalid_format", "message": str(exc)},
            ) from exc
        return {"ok": True, "format": item.model_dump(mode="json")}
