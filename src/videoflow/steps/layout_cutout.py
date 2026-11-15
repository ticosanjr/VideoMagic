"""Plan retention-oriented cutout/PIP/full-screen layouts for Shorts."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class CutoutParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: str = Field(default="auto", pattern="^(auto|callaway|rounded_window|full_screen)$")
    head_overlap: float = Field(default=0.12, ge=0.0, le=0.4)
    corner_radius: float = Field(default=0.08, ge=0.0, le=0.5)
    margin: float = Field(default=0.04, ge=0.0, le=0.3)
    matte_source: str = Field(default="auto", pattern="^(auto|matte|segmentation|none)$")
    transition: str = Field(default="cut", pattern="^(cut|fade|slide)$")


@register_step
class CutoutLayoutStep(BaseStep):
    type = "layout.cutout"
    status = "partial"
    icon = "▣"
    color = "#14b8a6"
    title = "Cutout layout"
    description = "Plan presenter cutouts, rounded windows, and full-screen alternation."
    requires = ()
    produces = ("layout_plan",)
    params_model = CutoutParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = CutoutParams.model_validate(params)
        plan = {
            "style": options.style,
            "head_overlap": options.head_overlap,
            "corner_radius": options.corner_radius,
            "margin": options.margin,
            "matte_source": options.matte_source,
            "transition": options.transition,
            "clips": [],
        }
        for index, short in enumerate(context.shorts):
            title = str(short.get("title") or f"short-{index + 1}")
            plan["clips"].append(
                {
                    "index": index,
                    "title": title,
                    "layout": "cutout" if options.style == "auto" else options.style,
                    "full_screen_when": "static > 5s or B-roll",
                }
            )
        path = context.work / "layout_plan.json"
        path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        context.metadata["layout_plan"] = plan
        context.artifacts["layout_plan"] = str(path)
        io.report(100, f"Cutout plan for {len(plan['clips'])} clip(s)")
