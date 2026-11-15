"""Wrap a step with structured repair attempts for an external coding agent."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.errors import SelfHealRequiredError
from videoflow.domain.headless import SelfHealReport
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import get_step, register_step


class SelfHealParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_step: str
    target_params: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int = Field(default=3, ge=1, le=10)
    retry_on: list[str] = Field(default_factory=lambda: ["ffmpeg", "syntax", "render", "self_heal"])
    repair_context: bool = True


@register_step
class SelfHealStep(BaseStep):
    type = "step.self_heal"
    status = "available"
    icon = "⟳"
    color = "#f97316"
    title = "Self-heal step"
    description = (
        "Run a target step and return structured stderr/context to OpenCode for "
        "repair before a human gate."
    )
    requires = ()
    produces = ("self_heal_report",)
    params_model = SelfHealParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = SelfHealParams.model_validate(params)
        target = get_step(options.target_step)
        last_error: Exception | None = None
        for attempt in range(1, options.max_attempts + 1):
            io.check_cancel()
            try:
                target.run(
                    context,
                    target.params_model.model_validate(options.target_params),
                    io,
                )
            except Exception as exc:  # noqa: BLE001 - repair loop
                last_error = exc
                report = self._report(context, options, attempt, exc)
                context.metadata["self_heal_report"] = report
                self._write(context, report)
                io.emit(
                    "warning",
                    f"{options.target_step} attempt {attempt} failed: {exc}",
                    module="self_heal",
                )
                continue
            context.metadata["self_heal"] = {
                "step": options.target_step,
                "attempts": attempt,
                "ok": True,
            }
            io.report(100, f"{options.target_step} completed")
            return
        report = context.metadata.get("self_heal_report")
        if not isinstance(report, dict):
            report = self._report(context, options, options.max_attempts, last_error)
        raise SelfHealRequiredError(report)

    def _report(
        self,
        context: PipelineContext,
        options: SelfHealParams,
        attempt: int,
        exc: Exception | None,
    ) -> dict[str, object]:
        details = exc.to_dict() if hasattr(exc, "to_dict") else {}
        code = str(details.get("code") or "step_failed")
        message = str(details.get("message") or exc or "step failed")
        stderr = str(details.get("stderr") or "")
        command = str(details.get("command") or "")
        report = SelfHealReport(
            step=options.target_step,
            attempt=attempt,
            max_attempts=options.max_attempts,
            code=code,
            message=message,
            command=command,
            stderr=stderr[-8000:],
            returncode=(
                int(details["returncode"]) if isinstance(details.get("returncode"), int) else None
            ),
            context={
                "output": str(context.output),
                "source": str(context.source),
                "warnings": list(context.warnings),
                "hashes": dict(context.hashes),
                "metadata_keys": sorted(context.metadata),
            }
            if options.repair_context
            else {},
            partial_artifacts=sorted(str(path) for path in context.artifacts.values()),
        )
        return report.model_dump(mode="json")

    @staticmethod
    def _write(context: PipelineContext, report: dict[str, object]) -> None:
        path = context.work / "self_heal_report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
