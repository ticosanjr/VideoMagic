"""Phase-2 shell for computer-vision QA inspection."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class VisionQaParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_fps: float = Field(default=10.0, gt=0.0, le=60.0)
    max_flash_frames: int = Field(default=3, ge=1, le=30)
    max_text_latency_ms: int = Field(default=100, ge=0, le=2000)
    max_lip_sync_frames: int = Field(default=2, ge=0, le=30)
    face_obscuration: bool = True
    checks: list[str] = Field(
        default_factory=lambda: [
            "duplicated_animations",
            "flash_frames",
            "text_latency",
            "face_obscuration",
            "stutter",
            "lip_sync",
        ]
    )


@register_step
class VisionQaStep(BaseStep):
    type = "qa.vision"
    title = "Vision QA (phase 2)"
    description = (
        "Plan the 10 fps vision inspection for flash frames, text latency, face "
        "obscuration, stutter, and lip-sync. The inspector lands in phase 2."
    )
    status = "planned"
    icon = "◉"
    color = "#22c55e"
    requires = ("export.video",)
    produces = ("vision_qa",)
    params_model = VisionQaParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = VisionQaParams.model_validate(params)
        plan = {
            "sample_fps": options.sample_fps,
            "max_flash_frames": options.max_flash_frames,
            "max_text_latency_ms": options.max_text_latency_ms,
            "max_lip_sync_frames": options.max_lip_sync_frames,
            "face_obscuration": options.face_obscuration,
            "checks": options.checks,
            "status": "phase_2_shell",
        }
        target = context.output / "qa" / "vision-plan.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        context.artifacts["vision_qa"] = str(target)
        context.metadata["vision_qa"] = plan
        context.warnings.append(
            "Vision QA is a phase-2 shell; no visual inspection was executed."
        )
        io.report(100, "Vision QA plan written (phase 2 shell)")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("vision_qa")
        return (Path(path),) if path else ()
