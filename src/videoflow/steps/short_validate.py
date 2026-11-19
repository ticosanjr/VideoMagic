"""Validate a Short composition plan before any render."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from videoflow.application.scene_intel.io import read_json, write_json
from videoflow.application.short_composition.validate import validate_plan
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ShortPlanError, StateNotReadyError
from videoflow.domain.scenes import ScenesManifest
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
        raw_plan: dict[str, Any] = {}
        if options.plan_path:
            raw_plan = read_json(Path(options.plan_path).expanduser())
        if not raw_plan:
            metadata = context.metadata.get("short_plan")
            if isinstance(metadata, dict):
                raw_plan = metadata
        if not raw_plan:
            artifact = context.artifacts.get("short_plan", "")
            if artifact:
                raw_plan = read_json(Path(artifact))
        if not raw_plan:
            raise StateNotReadyError("Run short.plan before short.validate")
        raw_manifest = context.metadata.get("scenes_manifest")
        if not isinstance(raw_manifest, dict) or not raw_manifest:
            artifact = context.artifacts.get("scenes_manifest", "")
            raw_manifest = read_json(Path(artifact)) if artifact else {}
        if not raw_manifest:
            raise StateNotReadyError("Run scene.analyze before short.validate")
        try:
            plan = ShortCompositionPlan.model_validate(raw_plan)
            manifest = ScenesManifest.model_validate(raw_manifest)
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
