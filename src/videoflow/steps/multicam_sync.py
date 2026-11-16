"""Multicam audio synchronization step."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.multicam import sync_multicam
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class MulticamParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_source_id: str = ""
    secondary_source_id: str = ""
    apply: bool = False
    min_confidence: float = Field(default=0.2, ge=0.0, le=1.0)
    compose: str = Field(default="none", pattern="^(none|pip|screen_face)$")
    pip_position: str = Field(
        default="top_right", pattern="^(top_left|top_right|bottom_left|bottom_right)$"
    )
    pip_width_ratio: float = Field(default=0.28, ge=0.08, le=0.8)


@register_step
class MulticamSyncStep(BaseStep):
    type = "sync.multicam_audio"
    title = "Multicam audio sync"
    description = "Align two sources with normalized audio cross-correlation."
    produces = ("multicam_manifest",)
    params_model = MulticamParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = MulticamParams.model_validate(params)
        if context.state is None:
            raise ValueError("Multicam sync requires a project timeline")
        io.report(20, "Extracting synchronization audio")
        report = sync_multicam(
            context.state,
            context.work / "multicam",
            primary_source_id=options.primary_source_id,
            secondary_source_id=options.secondary_source_id,
            apply=options.apply,
            min_confidence=options.min_confidence,
            compose=options.compose,
            pip_position=options.pip_position,
            pip_width_ratio=options.pip_width_ratio,
        )
        context.state = report["state"]  # type: ignore[assignment]
        context.metadata["multicam_report"] = report
        context.artifacts["multicam_manifest"] = str(report["manifest"])
        context.hashes["sync.multicam_audio"] = digest_payload(report)
        io.report(
            100,
            f"Multicam offset {report['offset_ms']}ms (confidence {report['confidence']})",
        )
