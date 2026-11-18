"""Delivery release-kit generation step."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from videoflow.application.release_kit import build_release_kit
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class ReleaseKitParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


@register_step
class ReleaseKitStep(BaseStep):
    type = "publish.release_kit"
    title = "Release kit"
    description = "Generate titles, chapters, hashtags, and thumbnail variants for publishing."
    produces = ("release_kit",)
    params_model = ReleaseKitParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        project_id = str(context.metadata.get("project_id") or "")
        if not project_id:
            io.report(100, "Release kit skipped: no project id")
            return
        kit = build_release_kit(project_id)
        context.artifacts["release_kit"] = str(kit.get("path") or "")
        context.metadata["release_kit"] = kit
        io.report(100, "Release kit ready")


__all__ = ["ReleaseKitStep"]
