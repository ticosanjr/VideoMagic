"""Consolidate final videos and exports into the delivery root."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from videoflow.application.output_layout import collect_outputs, delivery_root
from videoflow.application.projects import get_project
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import VideoFlowError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class CollectParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["copy", "move"] = "copy"
    project_id: str = ""


@register_step
class DeliveryCollectStep(BaseStep):
    type = "delivery.collect"
    title = "Collect final outputs"
    description = "Copy/move videos and exports under the workspace VideoFlow_Output root."
    requires = ()
    produces = ("delivery_manifest",)
    params_model = CollectParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = CollectParams.model_validate(params)
        requested = options.project_id or str(
            context.metadata.get("project_id") or context.output.name
        )
        try:
            project_id = get_project(requested).project_id
        except VideoFlowError:
            project_id = requested
        result = collect_outputs(
            context.output,
            project_id=project_id,
            mode=options.mode,
        )
        context.metadata["delivery_collect"] = result
        context.artifacts["delivery_collect"] = str(result["manifest_path"])
        io.emit(
            "info",
            f"{result['count']} final artifact(s) in {delivery_root()}",
            module="delivery.collect",
        )
        io.report(100, f"Collected {result['count']} artifact(s)")
