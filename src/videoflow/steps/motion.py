"""Phase-2 shell for programmatic motion-graphics rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class MotionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: Literal["hyperframes", "remotion", "fusion"] = "hyperframes"
    entry: str = ""
    fps: int = Field(default=30, ge=1, le=120)
    width: int = Field(default=1920, ge=16, le=7680)
    height: int = Field(default=1080, ge=16, le=4320)
    draft_scale: float = Field(default=0.5, gt=0.0, le=1.0)
    motion_blur: bool = False
    render_queue: Literal["single"] = "single"


@register_step
class MotionRenderStep(BaseStep):
    type = "motion.render"
    title = "Motion graphics (phase 2)"
    description = (
        "Plan a Hyperframes/Remotion/Fusion render. The actual renderer lands in "
        "phase 2; the node is bypassed until then."
    )
    status = "planned"
    icon = "▶"
    color = "#38bdf8"
    requires = ("edit.timeline",)
    produces = ("motion_plan",)
    params_model = MotionParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = MotionParams.model_validate(params)
        plan = {
            "engine": options.engine,
            "entry": options.entry,
            "fps": options.fps,
            "width": options.width,
            "height": options.height,
            "draft_scale": options.draft_scale,
            "motion_blur": options.motion_blur,
            "render_queue": options.render_queue,
            "status": "phase_2_shell",
        }
        target = context.output / "motion" / "plan.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        context.artifacts["motion_plan"] = str(target)
        context.metadata["motion_plan"] = plan
        context.warnings.append(
            "Motion graphics renderer is a phase-2 shell; no motion was rendered."
        )
        io.report(100, "Motion plan written (phase 2 shell)")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("motion_plan")
        return (Path(path),) if path else ()
