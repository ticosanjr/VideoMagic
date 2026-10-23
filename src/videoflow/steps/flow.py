"""Executable control-flow nodes for reusable recipes.

Flow nodes run a nested list of steps or reference another recipe. They keep the
same ``PipelineContext`` so downstream steps can consume whatever the branch
produced, and they report progress through the parent step's ``StepIO``.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import get_step, register_step

MAX_DEPTH = 6


class FlowStepSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


class FlowParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition: str = "always"
    recipe_id: str = ""
    steps: list[FlowStepSpec] = Field(default_factory=list)
    when_true: list[FlowStepSpec] = Field(default_factory=list)
    when_false: list[FlowStepSpec] = Field(default_factory=list)
    over: Literal["none", "shorts", "files"] = "none"
    glob: str = ""
    max_items: int = Field(default=20, ge=1, le=500)


def _recipe_steps(recipe_id: str) -> list[FlowStepSpec]:
    from videoflow.engine.recipes import get_recipe

    recipe = get_recipe(recipe_id)
    return [
        FlowStepSpec(type=step.type, params=dict(step.params))
        for step in recipe.steps
    ]


def _steps_from(params: FlowParams, *, branch: str = "") -> list[FlowStepSpec]:
    if branch == "true":
        return params.when_true or params.steps
    if branch == "false":
        return params.when_false
    if params.recipe_id:
        return _recipe_steps(params.recipe_id)
    return params.steps


def _condition_holds(params: FlowParams, context: PipelineContext) -> bool:
    condition = params.condition.strip().casefold()
    if condition in {"", "always", "true", "yes"}:
        return True
    if condition in {"never", "false", "no"}:
        return False
    if condition in {"has_shorts", "shorts"}:
        return bool(context.selected_shorts or context.shorts)
    if condition in {"has_transcript", "transcript"}:
        return bool(context.state and context.state.transcript or context.transcript)
    if condition.startswith("artifact:"):
        return bool(context.artifacts.get(condition.split(":", 1)[1]))
    if condition.startswith("metadata:"):
        key = condition.split(":", 1)[1]
        return bool(context.metadata.get(key))
    if condition.startswith("file:"):
        return Path(condition.split(":", 1)[1]).expanduser().is_file()
    raise ValueError(f"Unknown flow condition: {params.condition}")


def _run_steps(
    context: PipelineContext,
    steps: list[FlowStepSpec],
    io: StepIO,
    *,
    depth: int,
) -> None:
    if depth > MAX_DEPTH:
        raise ValueError("Flow nesting is too deep.")
    total = len(steps)
    for index, spec in enumerate(steps, start=1):
        step = get_step(spec.type)
        params = step.validate_params(spec.params)
        nested = replace(
            io,
            stage=f"{io.stage}/{index}:{spec.type}",
            index=index,
            total=max(1, total),
        )
        nested.report(max(1, int((index - 1) / max(1, total) * 100)), f"Running {step.title}")
        if step.bypass:
            continue
        if spec.type.startswith("flow."):
            step.run(context, params, nested)
        else:
            step.run(context, params, nested)


class _FlowStep(BaseStep):
    status = "available"
    icon = "◇"
    color = "#71717a"
    params_model = FlowParams

    def _execute_branch(
        self,
        context: PipelineContext,
        specs: list[FlowStepSpec],
        io: StepIO,
        *,
        label: str,
    ) -> None:
        if not specs:
            io.report(100, f"{label}: nothing to run")
            return
        _run_steps(context, specs, io, depth=int(context.metadata.get("_flow_depth", 0)) + 1)
        io.report(100, f"{label} finished")

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        raise NotImplementedError


@register_step
class ConditionalStep(_FlowStep):
    type = "flow.conditional"
    title = "Conditional"
    description = "Run one branch only when a condition is true."
    icon = "?"

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = FlowParams.model_validate(params)
        holds = _condition_holds(options, context)
        context.metadata["flow_last_condition"] = holds
        branch = _steps_from(options, branch="true" if holds else "false")
        self._execute_branch(
            context,
            branch,
            io,
            label=f"Conditional {'true' if holds else 'false'} branch",
        )


@register_step
class LoopStep(_FlowStep):
    type = "flow.loop"
    title = "Loop"
    description = "Repeat a subflow for every selected Short or matching file."
    icon = "↻"

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = FlowParams.model_validate(params)
        specs = _steps_from(options)
        if options.over == "shorts":
            items: list[dict[str, object]] = list(context.selected_shorts)
        elif options.over == "files":
            pattern = options.glob or "*"
            base = context.source.parent
            items = [
                {"path": str(path)}
                for path in sorted(base.glob(pattern))[: options.max_items]
                if path.is_file() and path != context.source
            ]
        else:
            items = []
        if not items:
            io.report(100, "Loop has no items")
            return
        for index, item in enumerate(items, start=1):
            context.metadata["loop_index"] = index
            context.metadata["loop_item"] = item
            _run_steps(context, specs, io, depth=int(context.metadata.get("_flow_depth", 0)) + 1)
            io.report(int(index / len(items) * 100), f"Loop {index}/{len(items)}")
        context.metadata.pop("loop_item", None)
        io.report(100, f"Loop finished ({len(items)} item(s))")


@register_step
class SubflowStep(_FlowStep):
    type = "flow.subflow"
    title = "Subflow"
    description = "Run a reusable recipe or an inline group of steps."
    icon = "▤"

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = FlowParams.model_validate(params)
        specs = _steps_from(options)
        self._execute_branch(context, specs, io, label="Subflow")
