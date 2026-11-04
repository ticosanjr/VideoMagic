"""Apply validated timeline actions proposed by an LLM.

Cuts are deliberately separated from style and zoom. ``llm.timeline`` can opt
into cut actions for advanced use, but the default and the dedicated ``llm.zoom``
and ``llm.style`` nodes never remove speech.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.llm_timeline import (
    ALLOWED_ACTIONS,
    PROMPT_HEADER,
    STYLE_ACTIONS,
    STYLE_HEADER,
    STYLE_ZOOM_HEADER,
    ZOOM_ACTIONS,
    ZOOM_HEADER,
    action_report,
    apply_actions,
    propose_actions,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import StateNotReadyError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class LlmActionsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = ""
    prompt: str = Field(
        default="Improve the edit without removing speech.",
        max_length=4000,
    )
    max_actions: int = Field(default=40, ge=1, le=200)


class LlmTimelineParams(LlmActionsParams):
    allow_cuts: bool = False
    prompt: str = Field(
        default=(
            "Choose content-aware zoom emphasis from the transcript text and "
            "use transitions and fades sparingly."
        ),
        max_length=4000,
    )


class LlmZoomParams(LlmActionsParams):
    prompt: str = Field(
        default=(
            "Choose subtle zooms on spoken emphasis: numbers, comparisons, "
            "reveals, and key claims. Never zoom silence."
        ),
        max_length=4000,
    )
    max_actions: int = Field(default=30, ge=1, le=200)


class LlmStyleParams(LlmActionsParams):
    prompt: str = Field(
        default=(
            "Choose sparse transitions and fades that support the story. "
            "Do not draw attention to non-speech clips."
        ),
        max_length=4000,
    )
    max_actions: int = Field(default=30, ge=1, le=200)


def _run_llm_actions(
    context: PipelineContext,
    io: StepIO,
    options: LlmActionsParams,
    *,
    header: str,
    allowed: set[str],
    module: str,
    report_key: str,
) -> None:
    if context.state is None:
        raise StateNotReadyError(f"{module} requires a timeline state")
    if io.llm_client is None:
        context.warnings.append(f"{module} skipped: no configured LLM provider")
        io.emit(
            "warning",
            f"{module} skipped: no configured LLM provider",
            module=module,
        )
        context.metadata[report_key] = action_report([], [], "skipped")
        return
    try:
        actions, reasoning = propose_actions(
            io.llm_client,
            options.prompt,
            context.state,
            header=header,
        )
    except Exception as exc:
        raise StateNotReadyError(f"{module} proposal failed: {exc}") from exc
    actions = actions[: options.max_actions]
    result = apply_actions(
        context.state,
        actions,
        allowed_actions=allowed,
    )
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
    context.metadata[report_key] = report
    if result.rejected:
        context.warnings.append(
            f"{module} rejected {len(result.rejected)} action(s); see {report_key}"
        )
    if result.normalized:
        message = (
            f"{module} closed {result.gaps_closed} gap(s) "
            f"({result.closed_seconds:.1f}s) to keep the export contiguous."
        )
        context.warnings.append(message)
        io.emit("warning", message, module=module)
    summary = (
        f"{module} applied {len(result.applied)}, "
        f"rejected {len(result.rejected)}"
    )
    if result.normalized:
        summary += f", closed {result.gaps_closed} gap(s)"
    io.report(100, summary)


@register_step
class LlmTimelineStep(BaseStep):
    type = "llm.timeline"
    title = "LLM timeline edit"
    description = (
        "Ask the configured LLM for timeline edits. By default it may only apply "
        "style and zoom; cut actions are opt-in via allow_cuts."
    )
    requires = ("edit.timeline",)
    produces = ("timeline", "llm_timeline_report")
    params_model = LlmTimelineParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = LlmTimelineParams.model_validate(params)
        allowed = ALLOWED_ACTIONS if options.allow_cuts else (STYLE_ACTIONS | ZOOM_ACTIONS)
        _run_llm_actions(
            context,
            io,
            options,
            header=PROMPT_HEADER if options.allow_cuts else STYLE_ZOOM_HEADER,
            allowed=allowed,
            module="LLM timeline edit",
            report_key="llm_timeline_report",
        )


@register_step
class LlmZoomStep(BaseStep):
    type = "llm.zoom"
    title = "LLM zoom"
    description = (
        "Choose content-aware zoom emphasis from the transcript text. Never "
        "changes the cut list and never zooms non-speech clips."
    )
    requires = ("edit.timeline",)
    produces = ("timeline", "llm_zoom_report")
    params_model = LlmZoomParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = LlmZoomParams.model_validate(params)
        _run_llm_actions(
            context,
            io,
            options,
            header=ZOOM_HEADER,
            allowed=ZOOM_ACTIONS,
            module="LLM zoom",
            report_key="llm_zoom_report",
        )


@register_step
class LlmStyleStep(BaseStep):
    type = "llm.style"
    title = "LLM style"
    description = (
        "Choose sparse transitions, fades, scale, and position. Never changes "
        "the cut list."
    )
    requires = ("edit.timeline",)
    produces = ("timeline", "llm_style_report")
    params_model = LlmStyleParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = LlmStyleParams.model_validate(params)
        _run_llm_actions(
            context,
            io,
            options,
            header=STYLE_HEADER,
            allowed=STYLE_ACTIONS,
            module="LLM style",
            report_key="llm_style_report",
        )
