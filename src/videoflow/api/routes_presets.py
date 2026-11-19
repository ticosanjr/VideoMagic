"""Preset routes for node presets and global module presets."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from videoflow.application.node_presets import (
    NodePresetRequest,
    NodePresetUpdate,
    create_preset,
    delete_preset,
    update_preset,
)
from videoflow.application.node_presets import list_presets as list_node_presets
from videoflow.application.node_presets import set_favorite as set_preset_favorite
from videoflow.application.presets import get_preset, load_presets, save_preset


class PresetFavoriteRequest(BaseModel):
    favorite: bool = True


def register_preset_routes(app: FastAPI) -> None:
    """Register node-preset and global preset routes."""

    @app.get("/api/v1/node-presets")
    def node_presets(step_type: str = "") -> dict[str, object]:
        return {
            "ok": True,
            "presets": [
                preset.model_dump(mode="json")
                for preset in list_node_presets(step_type.strip())
            ],
        }

    @app.post("/api/v1/node-presets", status_code=201)
    def node_preset_create(request: NodePresetRequest) -> dict[str, object]:
        preset = create_preset(request)
        return {"ok": True, "preset": preset.model_dump(mode="json")}

    @app.patch("/api/v1/node-presets/{preset_id}")
    def node_preset_update(
        preset_id: str, request: NodePresetUpdate
    ) -> dict[str, object]:
        preset = update_preset(preset_id, request)
        return {"ok": True, "preset": preset.model_dump(mode="json")}

    @app.delete("/api/v1/node-presets/{preset_id}")
    def node_preset_delete(preset_id: str) -> dict[str, object]:
        delete_preset(preset_id)
        return {"ok": True, "deleted": preset_id}

    @app.post("/api/v1/node-presets/{preset_id}/favorite")
    def node_preset_favorite(
        preset_id: str, request: PresetFavoriteRequest
    ) -> dict[str, object]:
        preset = set_preset_favorite(preset_id, request.favorite)
        return {"ok": True, "preset": preset.model_dump(mode="json")}

    @app.get("/api/v1/presets")
    def list_presets() -> dict[str, object]:
        return {"ok": True, "presets": [entry.to_dict() for entry in load_presets()]}

    @app.get("/api/v1/presets/{name}")
    def read_preset(name: str) -> dict[str, object]:
        return {"ok": True, "preset": get_preset(name).to_dict()}

    @app.put("/api/v1/presets/{name}")
    def write_preset(name: str, payload: dict[str, Any]) -> dict[str, object]:
        return {"ok": True, "preset": save_preset(name, payload).to_dict()}
