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


@dataclass(frozen=True, slots=True)
class PortSpec:
    """One typed input or output exposed by a step."""

    id: str
    label: str
    type: str
    context_key: str
    required: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "required": self.required,
        }


@dataclass
class StepIO:
    stage: str = "step"
    index: int = 1
    total: int = 1
    adapter: Any | None = None
    llm_client: Any | None = None
    asr_client: Any | None = None
    progress: Callable[[str, int, str], None] | None = None
    step_progress: Callable[[str, int, str], None] | None = None
    should_cancel: Callable[[], bool] | None = None
    cancel_event: Any | None = None
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
        if self.step_progress is not None:
            self.step_progress(self.stage, local, message)
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
    status: str = "available"
    icon: str = "●"
    color: str = "#38bdf8"

    @property
    def bypass(self) -> bool:
        return self.status == "planned"

    @abstractmethod
    def run(self, context: Any, params: BaseModel, io: StepIO) -> None:
        """Mutate the context in place. Raise VideoFlowError on expected failure."""

    def validate_params(self, payload: dict[str, Any] | None) -> BaseModel:
        return self.params_model.model_validate(payload or {})

    def is_cacheable(self, params: BaseModel) -> bool:
        """Whether this step may reuse a checkpoint with these params."""

        return True

    def cache_outputs(self, context: Any) -> tuple[Any, ...]:
        """Files that must still exist before a checkpoint can be reused."""

        return ()

    @property
    def input_ports(self) -> tuple[PortSpec, ...]:
        from videoflow.steps.ports import ports_for_type

        return ports_for_type(self.type)[0]

    @property
    def output_ports(self) -> tuple[PortSpec, ...]:
        from videoflow.steps.ports import ports_for_type

        return ports_for_type(self.type)[1]

    def manifest(self) -> dict[str, Any]:
        from videoflow.steps.field_metadata import apply_field_metadata

        schema = apply_field_metadata(
            self.type,
            self.title,
            self.params_model.model_json_schema(),
        )
        return {
            "type": self.type,
            "title": self.title,
            "description": self.description,
            "requires": list(self.requires),
            "produces": list(self.produces),
            "params_schema": schema,
            "inputs": [port.to_dict() for port in self.input_ports],
            "outputs": [port.to_dict() for port in self.output_ports],
            "status": self.status,
            "icon": self.icon,
            "color": self.color,
            "bypass": self.bypass,
        }
