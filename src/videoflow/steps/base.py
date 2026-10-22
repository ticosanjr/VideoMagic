"""Atomic pipeline step protocol.

A step is a pure-ish transformation over ``PipelineContext`` plus validated
parameters. Progress, cancellation, logging, and external clients arrive through
``StepIO`` so a step can run from a recipe, the API, the CLI, or MCP.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict


class EmptyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass
class StepIO:
    stage: str = "step"
    index: int = 1
    total: int = 1
    adapter: Any | None = None
    llm_client: Any | None = None
    asr_client: Any | None = None
    progress: Callable[[str, int, str], None] | None = None
    should_cancel: Callable[[], bool] | None = None
    log: Callable[[str, str, str], None] | None = None

    def check_cancel(self) -> None:
        if self.should_cancel is not None and self.should_cancel():
            from videoflow.domain.errors import JobCancelledError

            raise JobCancelledError("Job cancelled")

    def report(self, percent: int, message: str) -> None:
        self.check_cancel()
        if self.progress is None:
            return
        local = max(0, min(100, int(percent)))
        overall = int(((self.index - 1) * 100 + local) / max(1, self.total))
        self.progress(self.stage, overall, message)

    def emit(self, level: str, message: str, *, module: str | None = None) -> None:
        if self.log is not None:
            self.log(module or self.stage, level, message)


class BaseStep(ABC):
    """Base class for recipe steps."""

    type: str = "base"
    version: str = "1"
    title: str = "Base"
    description: str = ""
    requires: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    params_model: type[BaseModel] = EmptyParams

    @abstractmethod
    def run(self, context: Any, params: BaseModel, io: StepIO) -> None:
        """Mutate the context in place. Raise VideoFlowError on expected failure."""

    def validate_params(self, payload: dict[str, Any] | None) -> BaseModel:
        return self.params_model.model_validate(payload or {})

    def cache_outputs(self, context: Any) -> tuple[Any, ...]:
        """Files that must still exist before a checkpoint can be reused."""

        return ()

    def manifest(self) -> dict[str, Any]:
        schema = self.params_model.model_json_schema()
        return {
            "type": self.type,
            "title": self.title,
            "description": self.description,
            "requires": list(self.requires),
            "produces": list(self.produces),
            "params_schema": schema,
        }
