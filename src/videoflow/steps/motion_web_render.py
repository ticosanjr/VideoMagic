"""Bridge for Hyperframes/Remotion/HTML scene rendering."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.web_render import render_html_scene
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import RecipeError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class WebRenderParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: str = Field(default="auto", pattern="^(auto|html|hyperframes|remotion)$")
    project_path: str = ""
    entry: str = "index.html"
    command: str = ""
    duration_sec: float = Field(default=5.0, gt=0.0, le=3600.0)
    width: int = Field(default=1920, ge=16, le=7680)
    height: int = Field(default=1080, ge=16, le=4320)
    fps: int = Field(default=30, ge=1, le=120)
    alpha: bool = False
    draft_scale: float = Field(default=1.0, ge=0.1, le=1.0)
    motion_blur: bool = True
    output_format: str = Field(default="mp4", pattern="^(mp4|mov|webm)$")


@register_step
class WebRenderStep(BaseStep):
    type = "motion.web_render"
    status = "partial"
    icon = "◫"
    color = "#ec4899"
    title = "Web scene render"
    description = "Render HTML/Hyperframes/Remotion scenes through an explicit local command."
    requires = ()
    produces = ("motion_assets",)
    params_model = WebRenderParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = WebRenderParams.model_validate(params)
        project = (
            Path(options.project_path).expanduser() if options.project_path else context.output
        )
        target = context.work / f"motion-scene.{options.output_format}"
        if not options.command.strip():
            entry = project / options.entry if project.is_dir() else project
            if options.engine in {"auto", "html"} and entry.is_file():
                rendered = render_html_scene(
                    project,
                    options.entry,
                    target,
                    duration_sec=options.duration_sec,
                    fps=options.fps,
                    width=options.width,
                    height=options.height,
                    alpha=options.alpha,
                    draft_scale=options.draft_scale,
                )
                assets = [
                    {
                        "kind": "motion",
                        "path": str(rendered),
                        "width": int(options.width * options.draft_scale),
                        "height": int(options.height * options.draft_scale),
                        "fps": options.fps,
                        "alpha": options.alpha,
                        "draft": options.draft_scale < 1.0,
                        "engine": "html",
                    }
                ]
                context.metadata["motion_assets"] = assets
                context.artifacts["motion_assets"] = str(rendered)
                io.report(100, "HTML scene rendered")
                return
            raise RecipeError(
                "motion.web_render needs an HTML entry or a render command "
                "(Remotion/Hyperframes). Set `command` with {output}, {project}, "
                "{fps}, {width}, {height}."
            )
        command = options.command.format(
            output=str(target),
            project=str(project),
            entry=options.entry,
            fps=options.fps,
            width=max(16, int(options.width * options.draft_scale)),
            height=max(16, int(options.height * options.draft_scale)),
            duration=options.duration_sec,
        )
        io.report(10, "Starting web scene render")
        completed = subprocess.run(
            shlex.split(command),
            cwd=str(project if project.is_dir() else context.output),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            from videoflow.domain.errors import IngestError

            raise IngestError(f"motion.web_render failed: {completed.stderr.strip()[-1000:]}")
        if not target.is_file():
            raise RecipeError(f"motion.web_render did not produce {target}")
        assets = [
            {
                "kind": "motion",
                "path": str(target),
                "width": int(options.width * options.draft_scale),
                "height": int(options.height * options.draft_scale),
                "fps": options.fps,
                "alpha": options.alpha,
                "draft": options.draft_scale < 1.0,
            }
        ]
        context.metadata["motion_assets"] = assets
        context.artifacts["motion_assets"] = str(target)
        io.report(100, "Web scene rendered")
