"""Discovery routes: node options, capabilities, steps, and the recipe list."""

from __future__ import annotations

from fastapi import FastAPI

from videoflow.application import recipe_meta
from videoflow.application.capabilities import (
    capability_manifest,
    external_services_allowed,
)
from videoflow.application.models import list_models
from videoflow.application.providers import list_providers
from videoflow.application.service_definitions import list_definitions
from videoflow.engine.recipes import list_recipes
from videoflow.steps import manifest as step_manifest


def register_discovery_routes(app: FastAPI) -> None:
    """Register the read-only discovery surface used by the studio."""

    @app.get("/api/v1/node-options")
    def node_options() -> dict[str, object]:
        providers: dict[str, list[dict[str, object]]] = {}
        for item in list_providers():
            capability = str(item.get("capability") or "")
            providers.setdefault(capability, []).append(item)
        return {
            "ok": True,
            "providers": providers,
            "services": [item.model_dump(mode="json") for item in list_definitions()],
            "models": list_models(),
        }

    @app.get("/api/v1/capabilities")
    def capabilities(allow_external: bool = False) -> dict[str, object]:
        return {
            "ok": True,
            "external_services_allowed": external_services_allowed(allow_external),
            "capabilities": capability_manifest(allow_external_services=allow_external),
        }

    @app.get("/api/v1/steps")
    def list_steps() -> dict[str, object]:
        return {"ok": True, "steps": step_manifest()}

    @app.get("/api/v1/recipes")
    def recipes() -> dict[str, object]:
        return {"ok": True, "recipes": recipe_meta.decorate(list_recipes())}
