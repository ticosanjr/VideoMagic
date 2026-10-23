"""Planned control-flow nodes for reusable recipes."""

from __future__ import annotations

from pydantic import BaseModel

from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, EmptyParams, StepIO
from videoflow.steps.registry import register_step


class _FlowStep(BaseStep):
    status = "planned"
    icon = "◇"
    color = "#71717a"
    params_model = EmptyParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        io.report(100, "Bypassed")


@register_step
class ConditionalStep(_FlowStep):
    type = "flow.conditional"
    title = "Conditional"
    description = "Planned: run a branch only when a condition is true."
    icon = "?"


@register_step
class LoopStep(_FlowStep):
    type = "flow.loop"
    title = "Loop"
    description = "Planned: repeat a subflow for each file or Short."
    icon = "↻"


@register_step
class SubflowStep(_FlowStep):
    type = "flow.subflow"
    title = "Subflow"
    description = "Planned: reusable group of steps."
    icon = "▤"
