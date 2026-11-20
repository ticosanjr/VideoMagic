"""Short delivery QA: render, captions, safe zones, and FCPXML."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.scene_intel.io import write_json
from videoflow.application.short_composition.io import (
    read_cues,
    read_export_report,
    read_plan,
)
from videoflow.application.short_composition.qa import validate_short_delivery
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import NeedsReviewError
from videoflow.domain.short_composition import ShortCompositionPlan
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class ShortQaParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_path: str = ""
    video_path: str = ""
    cues_path: str = ""
    export_report_path: str = ""
    strict: bool = True


def _plan(context: PipelineContext, override: str) -> ShortCompositionPlan:
    return read_plan(context, override, step="short.qa")


@register_step
class ShortQaStep(BaseStep):
    type = "short.qa"
    title = "Short delivery QA"
    description = (
        "Check the rendered 1080x1920 output, caption spans, Shorts safe zones, "
        "duration, and FCPXML track validation."
    )
    status = "available"
    icon = "✓"
    color = "#22c55e"
    requires = ("short.export",)
    produces = ("short_qa",)
    params_model = ShortQaParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ShortQaParams.model_validate(params)
        plan = _plan(context, options.plan_path)
        cues = read_cues(context, options.cues_path)
        export_report = read_export_report(context, options.export_report_path)
        video = (
            Path(options.video_path).expanduser()
            if options.video_path
            else Path(context.artifacts.get("short_render", ""))
        )
        width = height = 0
        duration = 0.0
        if video.is_file():
            try:
                media = FFmpegAdapter().probe(video)
                width, height = media.width, media.height
                duration = media.duration_frames * media.fps_den / max(1, media.fps_num)
            except Exception as exc:  # noqa: BLE001 - QA reports the probe failure
                context.warnings.append(f"Short QA probe failed: {exc}")
        report = validate_short_delivery(
            plan,
            cues,
            render_path=video if video.is_file() else None,
            render_width=width,
            render_height=height,
            render_duration=duration,
            fcpxml_report=export_report,
        )
        target = (
            Path(context.output)
            / "shorts"
            / plan.short_id
            / "short_qa.json"
        )
        write_json(target, report)
        context.metadata["short_qa"] = report
        context.artifacts["short_qa"] = str(target)
        context.hashes["short.qa"] = digest_payload(report)
        for warning in report["warnings"]:
            if warning not in context.warnings:
                context.warnings.append(warning)
        if report["errors"] and options.strict:
            raise NeedsReviewError(
                "Short delivery QA found issues: "
                + "; ".join(str(item) for item in report["errors"]),
                report=report,
            )
        io.report(
            100,
            "Short QA passed" if report["ok"] else "Short QA needs review",
        )


__all__ = ["ShortQaParams", "ShortQaStep"]
