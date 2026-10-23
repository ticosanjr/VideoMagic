"""Declarative recipe contract.

A recipe is a versioned DAG of steps. The JSON file is the contract shared by
the CLI, REST API, MCP tools, and the visual editor.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from videoflow.domain.errors import RecipeError
from videoflow.domain.migrations import migrate_recipe

STEP_ID = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{0,63}$")
RECIPE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LlmRecipeConfig(StrictModel):
    """Provider selection for optional LLM steps.

    Secrets are referenced by environment variable name, never stored inline.
    """

    provider: Literal["openai_compatible", "opencode", "none"] = "none"
    base_url: str | None = None
    model: str = ""
    api_key_env: str = "VIDEOWFLOW_LLM_API_KEY"
    timeout_seconds: float = Field(default=90.0, gt=0.0, le=600.0)


class RecipeNodeUi(StrictModel):
    x: float = 0.0
    y: float = 0.0
    expanded: bool = False
    pinned: bool = False
    width: int = Field(default=420, ge=280, le=900)


class RecipeViewport(StrictModel):
    x: float = 0.0
    y: float = 0.0
    zoom: float = Field(default=1.0, gt=0.0, le=4.0)


class RecipeUi(StrictModel):
    version: int = Field(default=1, ge=1)
    viewport: RecipeViewport = Field(default_factory=RecipeViewport)
    nodes: dict[str, RecipeNodeUi] = Field(default_factory=dict)


class RecipeStep(StrictModel):
    id: str
    type: str = Field(min_length=1)
    needs: list[str] = Field(default_factory=list)
    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        if not STEP_ID.match(value):
            raise ValueError("step id must start with a letter and contain [A-Za-z0-9_.-]")
        return value


class Recipe(StrictModel):
    schema_version: Literal[1] = 1
    id: str
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    llm: LlmRecipeConfig = Field(default_factory=LlmRecipeConfig)
    ui: RecipeUi = Field(default_factory=RecipeUi)
    steps: list[RecipeStep] = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def valid_recipe_id(cls, value: str) -> str:
        if not RECIPE_ID.match(value):
            raise ValueError("recipe id must contain [A-Za-z0-9_.-]")
        return value

    def validate_graph(
        self,
        known_types: set[str] | None = None,
        *,
        requires_by_type: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        """Reject duplicate ids, unknown dependencies, unknown types, and cycles."""

        ids = [step.id for step in self.steps]
        duplicates = sorted({step_id for step_id in ids if ids.count(step_id) > 1})
        if duplicates:
            raise RecipeError(f"Duplicate step ids: {', '.join(duplicates)}")
        known = set(ids)
        for step in self.steps:
            if known_types is not None and step.type not in known_types:
                raise RecipeError(f"Step {step.id!r} uses unknown type {step.type!r}")
            for dependency in step.needs:
                if dependency == step.id:
                    raise RecipeError(f"Step {step.id!r} cannot depend on itself")
                if dependency not in known:
                    raise RecipeError(
                        f"Step {step.id!r} needs unknown step {dependency!r}"
                    )
        order = self.topological_order()
        if requires_by_type:
            by_id = {step.id: step for step in order}
            for step in order:
                ancestors: set[str] = set()
                stack = list(step.needs)
                while stack:
                    dependency = stack.pop()
                    if dependency in ancestors:
                        continue
                    ancestors.add(dependency)
                    stack.extend(by_id[dependency].needs)
                provided = {by_id[item].type for item in ancestors}
                missing = sorted(
                    set(requires_by_type.get(step.type, ())) - provided
                )
                if missing:
                    raise RecipeError(
                        f"Step {step.id!r} ({step.type}) requires missing upstream "
                        f"step types: {', '.join(missing)}"
                    )

    def enabled_steps(self) -> list[RecipeStep]:
        return [step for step in self.steps if step.enabled]

    def topological_order(self) -> list[RecipeStep]:
        """Return enabled steps in dependency order (stable within a level)."""

        enabled = {step.id: step for step in self.enabled_steps()}
        for step in enabled.values():
            for dependency in step.needs:
                if dependency not in enabled:
                    raise RecipeError(
                        f"Step {step.id!r} needs disabled or missing step {dependency!r}"
                    )
        indegree = {step_id: len(step.needs) for step_id, step in enabled.items()}
        children: dict[str, list[str]] = defaultdict(list)
        for step in enabled.values():
            for dependency in step.needs:
                children[dependency].append(step.id)
        ready = [step_id for step_id, degree in indegree.items() if degree == 0]
        ordered: list[RecipeStep] = []
        while ready:
            current = ready.pop(0)
            ordered.append(enabled[current])
            for child in children[current]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
        if len(ordered) != len(enabled):
            cycle = sorted(step_id for step_id, degree in indegree.items() if degree > 0)
            raise RecipeError(f"Recipe contains a dependency cycle: {', '.join(cycle)}")
        return ordered

    def uses_llm(self) -> bool:
        return any(
            step.enabled
            and step.type
            in {
                "retakes.cull",
                "shorts.select",
                "transcribe.auto",
            }
            for step in self.steps
        )


def parse_recipe(payload: dict[str, Any]) -> Recipe:
    try:
        return Recipe.model_validate(migrate_recipe(payload))
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first.get("loc", ()))
        message = first.get("msg", "invalid recipe")
        raise RecipeError(f"{location or 'recipe'}: {message}") from exc


def load_recipe(path: Path) -> Recipe:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RecipeError(f"Cannot read recipe {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RecipeError(f"Recipe {path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RecipeError("Recipe root must be a JSON object")
    return parse_recipe(payload)


def recipe_to_dict(recipe: Recipe) -> dict[str, Any]:
    return recipe.model_dump(mode="json")
