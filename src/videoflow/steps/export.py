"""NLE export step."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.export_service import export_timeline
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import StateNotReadyError
from videoflow.exporters.fcpxml import Dialect
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class ExportParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    targets: list[Literal["resolve", "premiere", "kdenlive", "mp4"]] = Field(
        default_factory=lambda: ["resolve", "premiere", "kdenlive"]
    )
    dialect: Dialect = "1.9"
    subdir: str = "exports"


@register_step
class ExportStep(BaseStep):
    type = "export.nle"
    title = "Export timelines"
    description = "Write FCPXML, XMEML, Kdenlive, and/or a direct MP4 from the same timeline."
    requires = ("edit.timeline",)
    produces = ("nle_artifacts",)
    params_model = ExportParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ExportParams.model_validate(params)
        if context.state is None:
            raise StateNotReadyError("The export step requires a built timeline")
        destination = context.output / options.subdir
        destination.mkdir(parents=True, exist_ok=True)
        io.report(20, "Writing NLE timelines")
        artifacts = export_timeline(
            context.state,
            destination,
            targets=options.targets,
            dialect=options.dialect,
        )
        context.artifacts.update({name: str(path) for name, path in artifacts.items()})
        context.hashes["export"] = digest_payload(
            {name: str(path) for name, path in artifacts.items()}
        )
        io.report(100, f"{len(artifacts)} NLE artifacts written")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(Path(path) for path in context.artifacts.values())
