"""Batch execution routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field, model_validator

from videoflow.core.recipe import parse_recipe
from videoflow.domain.paths import resolve_allowed
from videoflow.engine.batch import BatchManager
from videoflow.engine.recipes import (
    get_recipe,
    resolve_recipe_paths,
)
from videoflow.runtime import allowed_roots
from videoflow.steps import requirements_by_type, step_types
from videoflow.steps.ports import validate_recipe_ports


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


def register_batch_routes(app: FastAPI, batch_manager: BatchManager) -> None:
    """Register batch creation, listing, resume, and cancellation routes."""

    @app.post("/api/v1/batches", status_code=202)
    def create_batch(request: BatchRequest) -> dict[str, object]:
        roots = allowed_roots()
        source_dir = resolve_allowed(Path(request.source_dir), roots)
        output_root = resolve_allowed(Path(request.output_root), roots)
        if request.recipe is not None:
            recipe = parse_recipe(request.recipe)
        else:
            recipe = get_recipe(str(request.recipe_id))
        recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
        validate_recipe_ports(recipe)
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
        return {"ok": True, "batch": batch.to_dict()}

    @app.get("/api/v1/batches")
    def list_batches(limit: int | None = None, offset: int = 0) -> dict[str, object]:
        batches = batch_manager.list(limit=limit, offset=offset)
        return {
            "ok": True,
            "batches": [batch.to_dict() for batch in batches],
            "total": len(batch_manager.list()),
        }

    @app.post("/api/v1/batches/{batch_id}/resume")
    def resume_batch(batch_id: str) -> dict[str, object]:
        batch = batch_manager.resume(batch_id)
        return {"ok": True, "batch": batch.to_dict()}

    @app.get("/api/v1/batches/{batch_id}")
    def get_batch(batch_id: str) -> dict[str, object]:
        batch = batch_manager.get(batch_id)
        return {"ok": True, "batch": batch.to_dict()}

    @app.post("/api/v1/batches/{batch_id}/cancel")
    def cancel_batch(batch_id: str) -> dict[str, object]:
        batch = batch_manager.cancel(batch_id)
        return {"ok": True, "batch": batch.to_dict()}
