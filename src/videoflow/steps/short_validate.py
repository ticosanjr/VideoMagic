"""Validate a Short composition plan before any render."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from videoflow.application.scene_intel.io import write_json
from videoflow.application.short_composition.io import read_manifest, read_optional_plan
from videoflow.application.short_composition.validate import validate_plan
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ShortPlanError, StateNotReadyError
from videoflow.domain.short_composition import ShortCompositionPlan
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class ShortValidateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_path: str = ""
    strict: bool = True


@register_step
class ShortValidateStep(BaseStep):
    type = "short.validate"
    title = "Validate Short plan"
    description = (
        "Check coverage, durations, layouts, B-roll, upscale, crops, captions, "
        "and Shorts safe zones before render."
    )
    status = "available"
    icon = "✓"
    color = "#22c55e"
    requires = ("short.plan",)
    produces = ("short_validation",)
    params_model = ShortValidateParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ShortValidateParams.model_validate(params)
        raw_plan = read_optional_plan(context, options.plan_path)
        if not raw_plan:
            raise StateNotReadyError("Run short.plan before short.validate")
        manifest = read_manifest(
            context,
            step="short.validate",
            error_prefix="Invalid plan or manifest",
        )
        try:
            plan = ShortCompositionPlan.model_validate(raw_plan)
        except ValueError as exc:
            raise ShortPlanError(f"Invalid plan or manifest: {exc}") from exc
        report = validate_plan(plan, manifest)
        target = (
            Path(context.output)
            / "shorts"
            / plan.short_id
            / "short_validation.json"
        )
        write_json(target, report)
        context.metadata["short_validation"] = report
        context.artifacts["short_validation"] = str(target)
        if report["errors"] and options.strict:
            raise ShortPlanError("; ".join(str(item) for item in report["errors"]))
        io.report(
            100,
            f"{report['segment_count']} segment(s) validated"
            if report["ok"]
            else "Short plan needs review",
        )


__all__ = ["ShortValidateParams", "ShortValidateStep"]
