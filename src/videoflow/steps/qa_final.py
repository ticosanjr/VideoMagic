"""Final MP4 QA step."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.qa_final import audit_final
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ExportError, NeedsReviewError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class FinalQaParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video_path: str = ""
    strict: bool = True
    mode: Literal["fast", "full"] = "full"
    collision_mode: Literal["visual", "rectangle"] = "visual"
    max_wer: float = Field(default=0.12, ge=0.0, le=1.0)


@register_step
class FinalQaStep(BaseStep):
    type = "qa.final"
    title = "Final MP4 QA"
    description = "Audit duration, frames, audio, captions, overlays, and word fidelity."
    produces = ("final_qa",)
    params_model = FinalQaParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = FinalQaParams.model_validate(params)
        if context.state is None:
            raise ExportError("Final QA requires a timeline")
        candidate = (
            Path(options.video_path).expanduser()
            if options.video_path
            else Path(
                context.artifacts.get("video")
                or context.artifacts.get("video_master")
                or context.output / "exports" / "youtube_master.mp4"
            )
        )
        if not candidate.is_file():
            raise ExportError(f"Final QA video does not exist: {candidate}")
        report = audit_final(
            candidate,
            output=context.output,
            state=context.state,
            strict=options.strict,
            mode=options.mode,
            collision_mode=options.collision_mode,
            max_wer=options.max_wer,
        )
        context.metadata["final_qa"] = report
        context.artifacts["final_qa"] = str(report.get("report") or "")
        if not report.get("ok"):
            raise NeedsReviewError(
                "Final QA needs review: " + str(report.get("status")),
                report=report,
            )
        io.report(100, "Final QA passed")


__all__ = ["FinalQaStep"]
