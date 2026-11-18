"""Final MP4 QA step."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from videoflow.application.qa_final import audit_final
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ExportError, NeedsReviewError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class FinalQaParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video_path: str = ""
    strict: bool = True


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
