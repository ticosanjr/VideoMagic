"""Test helpers for jobs that use the recipe execution path."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from videoflow.application.jobs import JobManager

MINIMAL_RECIPE: dict[str, Any] = {
    "schema_version": 1,
    "id": "test",
    "name": "Test",
    "steps": [{"id": "ingest", "type": "ingest", "needs": []}],
}


class _Result:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def to_dict(self) -> dict[str, Any]:
        return self._payload


class _RunnerAdapter:
    def __init__(self, runner: Callable[..., dict[str, Any]]) -> None:
        self._runner = runner

    def run(self, source: Path, output: Path, **kwargs: Any) -> _Result:
        return _Result(self._runner(source, output, **kwargs))


def manager_with_runner(
    runner: Callable[..., dict[str, Any]] | None = None,
    **kwargs: Any,
) -> JobManager:
    """Build a manager whose recipe runner delegates to a test fake."""

    factory = (
        (lambda _recipe, _job: _RunnerAdapter(runner))
        if runner is not None
        else None
    )
    return JobManager(recipe_runner_factory=factory, **kwargs)


def start_recipe(
    manager: JobManager,
    source: Path,
    output: Path,
    options: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Start a recipe job with the minimal valid recipe for test fakes."""

    merged = {"mode": "recipe", "recipe": MINIMAL_RECIPE, **(options or {})}
    return manager.start(source, output, merged, **kwargs)
