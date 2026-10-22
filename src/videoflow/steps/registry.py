"""Step registry. Only registered types can appear in a recipe."""

from __future__ import annotations

from collections.abc import Iterable

from videoflow.domain.errors import RecipeError
from videoflow.steps.base import BaseStep

_STEPS: dict[str, type[BaseStep]] = {}


def register_step(step: type[BaseStep]) -> type[BaseStep]:
    if not step.type or step.type == "base":
        raise ValueError("step type must be set")
    if step.type in _STEPS:
        raise ValueError(f"duplicate step type: {step.type}")
    _STEPS[step.type] = step
    return step


def get_step(step_type: str) -> BaseStep:
    try:
        return _STEPS[step_type]()
    except KeyError as exc:
        raise RecipeError(f"Unknown step type: {step_type}") from exc


def step_types() -> set[str]:
    return set(_STEPS)


def iter_steps() -> Iterable[BaseStep]:
    for step_type in sorted(_STEPS):
        yield _STEPS[step_type]()


def requirements_by_type() -> dict[str, tuple[str, ...]]:
    return {step.type: step.requires for step in iter_steps()}


def manifest() -> list[dict[str, object]]:
    return [step.manifest() for step in iter_steps()]
