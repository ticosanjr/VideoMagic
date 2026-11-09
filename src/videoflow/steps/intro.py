"""Intro compiler step."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.intro import compile_intro, write_manifest
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class IntroParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_sec: float = Field(default=112.0, ge=3.0, le=600.0)
    clip_seconds: float = Field(default=2.0, ge=0.5, le=10.0)
    max_assets: int = Field(default=60, ge=1, le=300)
    width: int = Field(default=1920, ge=16, le=7680)
    height: int = Field(default=1080, ge=16, le=4320)
    fps: int = Field(default=30, ge=1, le=120)
    title: str = Field(default="", max_length=200)
    manifest_path: str = Field(default="assets/manifest.json", max_length=2000)


@register_step
class IntroCompileStep(BaseStep):
    type = "intro.compile"
    title = "Compile intro"
    description = (
        "Build a fast-cut high-retention intro from approved assets, or a title "
        "card when no assets were harvested."
    )
    status = "available"
    icon = "⚡"
    color = "#f59e0b"
    params_model = IntroParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = IntroParams.model_validate(params)
        try:
            payload = json.loads(
                (context.output / options.manifest_path).read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            payload = {}
        assets = payload.get("assets", []) if isinstance(payload, dict) else []
        title = options.title or str(
            context.metadata.get("variables", {}).get("topic") or "VideoFlow"
        )
        result = compile_intro(
            context.output,
            assets=assets if isinstance(assets, list) else [],
            duration_sec=options.duration_sec,
            clip_seconds=options.clip_seconds,
            width=options.width,
            height=options.height,
            fps=options.fps,
            title=title,
            max_assets=options.max_assets,
        )
        manifest = write_manifest(context.output, result)
        context.metadata["intro"] = result
        context.artifacts["intro"] = result["path"]
        context.artifacts["intro_manifest"] = str(manifest)
        context.hashes["intro.compile"] = digest_payload(result)
        io.report(100, f"Intro compiled ({result['duration_sec']:.1f}s)")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("intro", "intro_manifest")
            if context.artifacts.get(key)
        )
