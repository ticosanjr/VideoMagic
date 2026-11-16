"""Plan retention-oriented cutout/PIP/full-screen layouts for Shorts."""

from __future__ import annotations

import json
from pathlib import Path

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
    render_preview: bool = False
    preview_seconds: float = Field(default=8.0, gt=0.0, le=60.0)
    draft_scale: float = Field(default=1.0, ge=0.1, le=1.0)


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
        if options.render_preview:
            preview = self._render_preview(context, options)
            if preview is not None:
                plan["preview"] = str(preview)
                context.artifacts["layout_preview"] = str(preview)
        io.report(100, f"Cutout plan for {len(plan['clips'])} clip(s)")

    @staticmethod
    def _render_preview(  # pragma: no cover - external FFmpeg renderer
        context: PipelineContext, options: CutoutParams
    ) -> Path | None:
        import subprocess

        from videoflow.application.render_gate import render_gate
        from videoflow.runtime import find_binary

        ffmpeg = find_binary("ffmpeg")
        if ffmpeg is None:
            context.warnings.append("layout.cutout preview requires FFmpeg")
            return None
        target = context.work / "layout-preview.mp4"
        if context.media is None:
            return None
        width = max(16, int(1080 * options.draft_scale))
        height = max(16, int(1920 * options.draft_scale))
        fg_width = max(16, int(900 * options.draft_scale))
        box_width = max(16, int(900 * options.draft_scale))
        background = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},boxblur=20:5,eq=brightness=-0.15"
        )
        foreground = f"scale={fg_width}:-2"
        filter_complex = (
            f"[0:v]{background}[bg];[0:v]{foreground}[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,"
            f"drawbox=x={(width - box_width) // 2}:y=(ih-ih*0.72)/2:"
            f"w={box_width}:h=ih*0.72:color=white@0.35:t=6[out]"
        )
        with render_gate.hold("layout.cutout", str(context.output)):
            completed = subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-t",
                    str(options.preview_seconds),
                    "-i",
                    str(context.source),
                    "-filter_complex",
                    filter_complex,
                    "-map",
                    "[out]",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-crf",
                    "22",
                    "-preset",
                    "veryfast",
                    "-an",
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        if completed.returncode != 0:
            context.warnings.append(
                f"layout.cutout preview failed: {completed.stderr.strip()[-400:]}"
            )
            return None
        return target
