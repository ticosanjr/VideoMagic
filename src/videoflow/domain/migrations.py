"""Version gates for persisted project and recipe JSON."""

from __future__ import annotations

from typing import Any

from videoflow.domain.errors import ProjectStateError, RecipeError

PROJECT_STATE_SCHEMA_VERSION = 1
RECIPE_SCHEMA_VERSION = 1


def migrate_project_state(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProjectStateError("Project state root must be a JSON object.")
    version = payload.get("schema_version", 1)
    if version != PROJECT_STATE_SCHEMA_VERSION:
        raise ProjectStateError(
            f"Unsupported project state schema_version {version}; "
            f"expected {PROJECT_STATE_SCHEMA_VERSION}."
        )
    migrated = dict(payload)
    migrated.setdefault("schema_version", PROJECT_STATE_SCHEMA_VERSION)
    return migrated


def migrate_recipe(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RecipeError("Recipe root must be a JSON object.")
    version = payload.get("schema_version", 1)
    if version != RECIPE_SCHEMA_VERSION:
        raise RecipeError(
            f"Unsupported recipe schema_version {version}; expected {RECIPE_SCHEMA_VERSION}."
        )
    migrated = dict(payload)
    migrated.setdefault("schema_version", RECIPE_SCHEMA_VERSION)
    migrated.setdefault("description", "")
    migrated.setdefault("llm", {})
    steps = migrated.get("steps")
    if isinstance(steps, list):
        migrated["steps"] = [
            {
                **step,
                "needs": step.get("needs", []),
                "enabled": step.get("enabled", True),
                "params": step.get("params", {}),
            }
            if isinstance(step, dict)
            else step
            for step in steps
        ]
    return migrated
