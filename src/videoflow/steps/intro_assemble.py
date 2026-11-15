"""Assemble an intro plan from the best already-mined body material."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.headless import IntroPlan
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class IntroAssembleParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_sec: float = Field(default=120.0, ge=5.0, le=600.0)
    source: str = Field(default="mixed", pattern="^(best_clips|motion|mixed)$")
    include_sfx: bool = True


@register_step
class IntroAssembleStep(BaseStep):
    type = "intro.assemble_last"
    status = "partial"
    icon = "▶"
    color = "#fb923c"
    title = "Assemble intro last"
    description = "Build a dense <2 min hook from the best clips and graphics already produced."
    requires = ()
    produces = ("intro_plan",)
    params_model = IntroAssembleParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = IntroAssembleParams.model_validate(params)
        segments: list[dict[str, object]] = []
        for index, short in enumerate(context.shorts[:5]):
            path = str(short.get("path") or "")
            if not path:
                continue
            segments.append(
                {
                    "index": index,
                    "title": str(short.get("title") or f"clip-{index + 1}"),
                    "path": path,
                    "duration_sec": float(short.get("duration_sec") or 0.0),
                }
            )
        for name in ("motion_assets", "render", "timeline"):
            value = context.artifacts.get(name)
            if value and len(segments) < 8:
                segments.append({"kind": name, "path": str(value)})
        sfx: list[str] = []
        if options.include_sfx:
            cues = context.metadata.get("sfx_cues")
            if isinstance(cues, list):
                sfx = [str(item.get("path")) for item in cues if isinstance(item, dict)]
        plan = IntroPlan(
            max_sec=options.max_sec,
            sources=[options.source],
            sfx=sfx[:12],
            segments=segments[:12],
        )
        context.metadata["intro_plan"] = plan.model_dump(mode="json")
        path = context.work / "intro_plan.json"
        path.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")
        context.artifacts["intro_plan"] = str(path)
        io.report(100, f"Intro plan with {len(plan.segments)} segment(s)")
