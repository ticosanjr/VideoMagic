"""Apply validated timeline actions proposed by an LLM."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.llm_timeline import (
    action_report,
    apply_actions,
    propose_actions,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import StateNotReadyError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class LlmTimelineParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = ""
    prompt: str = Field(
        default=(
            "Tighten the cut, remove weak starts, add tasteful zoom in/out, "
            "and use transitions sparingly."
        ),
        max_length=4000,
    )
    max_actions: int = Field(default=40, ge=1, le=200)


@register_step
class LlmTimelineStep(BaseStep):
    type = "llm.timeline"
    title = "LLM timeline edit"
    description = (
        "Ask the configured LLM for timeline cuts, crop in/out, zoom, transitions, "
        "fades, scale, and position, then apply only validated actions."
    )
    requires = ("edit.timeline",)
    produces = ("timeline", "llm_timeline_report")
    params_model = LlmTimelineParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = LlmTimelineParams.model_validate(params)
        if context.state is None:
            raise StateNotReadyError("LLM timeline edit requires a timeline state")
        if io.llm_client is None:
            context.warnings.append(
                "LLM timeline edit skipped: no configured LLM provider"
            )
            io.emit(
                "warning",
                "LLM timeline edit skipped: no configured LLM provider",
                module="llm.timeline",
            )
            context.metadata["llm_timeline_report"] = action_report([], [], "skipped")
            return
        try:
            actions, reasoning = propose_actions(
                io.llm_client, options.prompt, context.state
            )
        except Exception as exc:
            raise StateNotReadyError(f"LLM timeline proposal failed: {exc}") from exc
        actions = actions[: options.max_actions]
        result = apply_actions(context.state, actions)
        context.state = result.state
        report = action_report(
            result.applied,
            result.rejected,
            reasoning,
            normalized=result.normalized,
            gaps_closed=result.gaps_closed,
            closed_frames=result.closed_frames,
            closed_seconds=result.closed_seconds,
        )
        context.metadata["llm_timeline_report"] = report
        if result.rejected:
            context.warnings.append(
                f"LLM timeline rejected {len(result.rejected)} action(s); "
                "see llm_timeline_report"
            )
        if result.normalized:
            message = (
                f"LLM timeline closed {result.gaps_closed} gap(s) "
                f"({result.closed_seconds:.1f}s) to keep the export contiguous."
            )
            context.warnings.append(message)
            io.emit("warning", message, module="llm.timeline")
        summary = (
            f"LLM edits applied {len(result.applied)}, "
            f"rejected {len(result.rejected)}"
        )
        if result.normalized:
            summary += f", closed {result.gaps_closed} gap(s)"
        io.report(100, summary)
