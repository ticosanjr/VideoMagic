"""Recipe CRUD, validation, history, dry-run, and run routes."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field, ValidationError, model_validator

from videoflow.application import recipe_meta
from videoflow.application.jobs import JobManager
from videoflow.application.run_defaults import resolve_run_roots
from videoflow.core.recipe import parse_recipe, recipe_to_dict
from videoflow.domain.errors import RecipeError
from videoflow.engine.recipes import (
    get_recipe,
    get_recipe_version,
    list_recipe_history,
    resolve_recipe_paths,
    restore_recipe_version,
    save_user_recipe,
)
from videoflow.engine.runner import RecipeRunner
from videoflow.runtime import allowed_roots
from videoflow.steps import get_step, requirements_by_type, step_types
from videoflow.steps.ports import validate_recipe_ports


class RecipeFavoriteRequest(BaseModel):
    favorite: bool = True


class RecipeMetaRequest(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=30)


class RecipeRunRequest(BaseModel):
    source: str = ""
    output: str = ""
    recipe: dict[str, Any] | None = None
    recipe_id: str | None = None
    transcript_sentences: list[dict[str, Any]] = Field(default_factory=list)
    save_recipe: bool = False
    through: str | None = None
    resume: bool = True
    variables: dict[str, Any] = Field(default_factory=dict)
    profile: str | None = None
    idempotency_key: str | None = None

    @model_validator(mode="after")
    def exactly_one_recipe(self) -> RecipeRunRequest:
        if (self.recipe is None) == (self.recipe_id is None):
            raise ValueError("provide exactly one of recipe or recipe_id")
        return self


def start_recipe_job(
    request: RecipeRunRequest,
    through: str | None,
    jobs: JobManager,
) -> dict[str, object]:
    roots = allowed_roots()
    if request.recipe is not None:
        recipe = parse_recipe(request.recipe)
    else:
        recipe = get_recipe(str(request.recipe_id))
    recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
    if through is not None and through not in {
        step.id for step in recipe.enabled_steps()
    }:
        raise RecipeError(f"Unknown or disabled step: {through}")
    validate_recipe_ports(recipe, through=through)
    source, output = resolve_run_roots(
        recipe, request.source, request.output, roots
    )
    recipe = resolve_recipe_paths(recipe, roots)
    if request.save_recipe:
        save_user_recipe(recipe)
    job = jobs.start(
        source,
        output,
        {
            "mode": "recipe",
            "recipe": recipe.model_dump(mode="json"),
            "transcript_sentences": request.transcript_sentences,
            "through": through,
            "resume": request.resume,
            "variables": request.variables,
            "profile": request.profile,
        },
        queue=True,
        idempotency_key=request.idempotency_key,
    )
    recipe_meta.touch(recipe.id)
    return {"ok": True, "job": job.to_dict()}


def register_recipe_routes(app: FastAPI, jobs: JobManager) -> None:
    """Register recipe CRUD, validation, history, dry-run, and run routes."""

    @app.post("/api/v1/recipes/{recipe_id}/favorite")
    def favorite_recipe(
        recipe_id: str, request: RecipeFavoriteRequest
    ) -> dict[str, object]:
        get_recipe(recipe_id)
        entry = recipe_meta.set_favorite(recipe_id, request.favorite)
        return {"ok": True, "meta": entry.model_dump(mode="json")}

    @app.post("/api/v1/recipes/{recipe_id}/touch")
    def touch_recipe(recipe_id: str) -> dict[str, object]:
        get_recipe(recipe_id)
        entry = recipe_meta.touch(recipe_id)
        return {"ok": True, "meta": entry.model_dump(mode="json")}

    @app.patch("/api/v1/recipes/{recipe_id}/meta")
    def update_recipe_meta(
        recipe_id: str, request: RecipeMetaRequest
    ) -> dict[str, object]:
        get_recipe(recipe_id)
        entry = recipe_meta.set_tags(recipe_id, request.tags)
        return {"ok": True, "meta": entry.model_dump(mode="json")}

    @app.get("/api/v1/recipes/{recipe_id}")
    def recipe_detail(recipe_id: str) -> dict[str, object]:
        recipe = get_recipe(recipe_id)
        return {
            "ok": True,
            "recipe": recipe_to_dict(recipe),
            "meta": recipe_meta.get_meta(recipe.id).model_dump(mode="json"),
        }

    @app.put("/api/v1/recipes/{recipe_id}")
    def save_recipe(recipe_id: str, payload: dict[str, Any]) -> dict[str, object]:
        recipe = parse_recipe(payload)
        if recipe.id != recipe_id:
            raise RecipeError("recipe id does not match the URL")
        recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
        validate_recipe_ports(recipe)
        path = save_user_recipe(recipe)
        return {"ok": True, "recipe": recipe_to_dict(recipe), "path": str(path)}

    @app.get("/api/v1/recipes/{recipe_id}/history")
    def recipe_history(recipe_id: str) -> dict[str, object]:
        return {"ok": True, "history": list_recipe_history(recipe_id)}

    @app.get("/api/v1/recipes/{recipe_id}/history/{version}")
    def recipe_history_version(recipe_id: str, version: str) -> dict[str, object]:
        recipe = get_recipe_version(recipe_id, version)
        return {"ok": True, "recipe": recipe.model_dump(mode="json")}

    @app.post("/api/v1/recipes/{recipe_id}/history/{version}/restore")
    def restore_history(recipe_id: str, version: str) -> dict[str, object]:
        recipe = restore_recipe_version(recipe_id, version)
        return {"ok": True, "recipe": recipe_to_dict(recipe)}

    @app.post("/api/v1/recipes/validate")
    def validate_recipe(
        payload: dict[str, Any], through: str | None = None
    ) -> dict[str, object]:
        recipe = parse_recipe(payload)
        recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
        validate_recipe_ports(recipe, through=through)
        resolved = recipe.with_variables({})
        allowed = recipe.ids_through(through) if through is not None else None
        for step in resolved.steps:
            if allowed is not None and step.id not in allowed:
                continue
            try:
                get_step(step.type).validate_params(step.params)
            except ValidationError as exc:
                first = exc.errors()[0] if exc.errors() else {}
                raise RecipeError(
                    f"{step.id}: {first.get('msg', 'invalid parameters')}"
                ) from exc
        order = recipe.topological_order()
        return {
            "ok": True,
            "recipe": recipe_to_dict(recipe),
            "resolved": recipe_to_dict(resolved),
            "order": [step.id for step in order],
        }

    @app.post("/api/v1/recipes/dry-run")
    def recipe_dry_run(request: RecipeRunRequest) -> dict[str, object]:
        recipe = (
            parse_recipe(request.recipe)
            if request.recipe is not None
            else get_recipe(str(request.recipe_id))
        )
        recipe = resolve_recipe_paths(recipe, allowed_roots())
        plan = RecipeRunner(recipe).plan(
            variables=request.variables,
            profile=request.profile,
            through=request.through,
        )
        return plan

    @app.post("/api/v1/recipes/run", status_code=202)
    def run_recipe(request: RecipeRunRequest) -> dict[str, object]:
        return start_recipe_job(request, request.through, jobs)

    @app.post("/api/v1/steps/{step_id}/run", status_code=202)
    def run_step(step_id: str, request: RecipeRunRequest) -> dict[str, object]:
        return start_recipe_job(request, step_id, jobs)
