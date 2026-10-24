"""Human approval gates with pause/resume semantics."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ApprovalRequiredError, RecipeError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class GateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_id: str = Field(default="review", min_length=1, max_length=80)
    title: str = "Review"
    description: str = ""
    approve_label: str = "Approve"
    reject_label: str = "Reject"


@register_step
class HumanGateStep(BaseStep):
    type = "human.gate"
    title = "Human gate"
    description = "Pause the recipe until a human approves or rejects the current result."
    status = "available"
    icon = "◇"
    color = "#f59e0b"
    params_model = GateParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = GateParams.model_validate(params)
        path = context.output / "approvals" / f"{options.gate_id}.json"
        if not path.is_file():
            raise ApprovalRequiredError(
                options.gate_id,
                options.title,
                options.description or f"Approve {options.title} to continue.",
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RecipeError(f"Approval file is invalid: {path}") from exc
        if not payload.get("approved"):
            raise RecipeError(
                f"Gate {options.gate_id!r} was rejected"
                + (f": {payload.get('comment')}" if payload.get("comment") else "")
            )
        context.metadata[f"gate_{options.gate_id}"] = payload
        io.report(100, f"Gate {options.gate_id} approved")
