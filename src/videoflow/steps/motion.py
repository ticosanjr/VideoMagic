"""Motion scene generation and rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.motion import (
    build_scenes,
    render_scene,
    write_render_manifest,
    write_scenes,
)
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class MotionCodegenParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    units_path: str = Field(default="storyboard/units.json", max_length=2000)
    style_path: str = Field(default="style/style-guide.json", max_length=2000)
    assignments_path: str = Field(default="assets/assignments.json", max_length=2000)
    width: int = Field(default=1920, ge=16, le=7680)
    height: int = Field(default=1080, ge=16, le=4320)
    fps: int = Field(default=30, ge=1, le=120)
    max_scenes: int = Field(default=400, ge=1, le=1000)


def _read_json(path: Path, default: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


@register_step
class MotionCodegenStep(BaseStep):
    type = "motion.codegen"
    title = "Motion codegen"
    description = (
        "Turn units, style, and approved assets into a JSON scene graph with "
        "layers, titles, lower thirds, and timing."
    )
    status = "available"
    icon = "▶"
    color = "#38bdf8"
    params_model = MotionCodegenParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = MotionCodegenParams.model_validate(params)
        units_payload = _read_json(context.output / options.units_path, {})
        style_payload = _read_json(context.output / options.style_path, {})
        assignments_payload = _read_json(context.output / options.assignments_path, {})
        units = (
            units_payload.get("units", [])
            if isinstance(units_payload, dict)
            else units_payload
        )
        style = style_payload if isinstance(style_payload, dict) else {}
        assignments = (
            assignments_payload.get("assignments", [])
            if isinstance(assignments_payload, dict)
            else assignments_payload
        )
        assets: dict[str, list[dict[str, object]]] = {}
        for item in assignments if isinstance(assignments, list) else []:
            if not isinstance(item, dict) or not item.get("asset"):
                continue
            unit_id = str(item.get("unit_id") or "")
            asset = item.get("asset")
            if unit_id and isinstance(asset, dict):
                assets.setdefault(unit_id, []).append(
                    {
                        "path": asset.get("downloaded_path") or asset.get("path") or "",
                        "kind": asset.get("kind") or "image",
                    }
                )
        scenes = build_scenes(
            units if isinstance(units, list) else [],
            style=style,
            assets=assets,
            width=options.width,
            height=options.height,
            fps=options.fps,
            max_scenes=options.max_scenes,
        )
        target = write_scenes(context.output, scenes)
        context.metadata["motion_scenes"] = scenes
        context.artifacts["motion_scenes"] = str(target)
        context.hashes["motion.codegen"] = digest_payload(
            {"scenes": len(scenes), "width": options.width, "height": options.height}
        )
        io.report(100, f"{len(scenes)} motion scene(s) generated")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("motion_scenes")
        return (Path(path),) if path else ()


class MotionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: Literal["ffmpeg", "remotion", "hyperframes", "fusion"] = "ffmpeg"
    render: bool = True
    max_scenes: int = Field(default=400, ge=1, le=1000)
    width: int = Field(default=1920, ge=16, le=7680)
    height: int = Field(default=1080, ge=16, le=4320)
    fps: int = Field(default=30, ge=1, le=120)
    draft_scale: float = Field(default=1.0, gt=0.0, le=1.0)
    motion_blur: bool = False
    render_queue: Literal["single"] = "single"


@register_step
class MotionRenderStep(BaseStep):
    type = "motion.render"
    title = "Motion graphics"
    description = (
        "Render the JSON scene graph with FFmpeg and write an overlay manifest "
        "for the NLE export. Remotion is an optional alternative backend."
    )
    status = "available"
    icon = "▶"
    color = "#38bdf8"
    params_model = MotionParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = MotionParams.model_validate(params)
        plan = {
            "engine": options.engine,
            "render": options.render,
            "width": options.width,
            "height": options.height,
            "fps": options.fps,
            "max_scenes": options.max_scenes,
        }
        plan_path = context.output / "motion" / "plan.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        context.artifacts["motion_plan"] = str(plan_path)
        context.metadata["motion_plan"] = plan
        if not options.render:
            context.artifacts["motion_manifest"] = str(
                write_render_manifest(context.output, [])
            )
            io.report(100, "Motion render disabled")
            return
        if options.engine != "ffmpeg":
            context.warnings.append(
                f"Motion backend {options.engine} is not bundled; using the FFmpeg renderer."
            )
        target = context.output / "motion" / "scenes.json"
        payload = _read_json(target, {})
        scenes = payload.get("scenes") if isinstance(payload, dict) else []
        if not isinstance(scenes, list) or not scenes:
            context.warnings.append("Motion render skipped: no scenes generated.")
            context.artifacts["motion_manifest"] = str(
                write_render_manifest(context.output, [])
            )
            io.report(100, "No motion scenes; render skipped")
            return
        rendered: list[dict[str, object]] = []
        warnings: list[str] = []
        for index, scene in enumerate(scenes[: options.max_scenes], start=1):
            if not isinstance(scene, dict):
                continue
            io.report(
                int((index - 1) / max(1, len(scenes[: options.max_scenes])) * 100),
                f"Rendering motion scene {index}",
            )
            try:
                path = render_scene(scene, context.output / "motion" / "rendered")
                rendered.append(
                    {
                        "scene_id": scene.get("scene_id"),
                        "unit_id": scene.get("unit_id"),
                        "title": scene.get("title"),
                        "path": str(path),
                        "start_sec": float(scene.get("start_sec") or 0.0),
                        "duration_sec": float(scene.get("duration_sec") or 0.0),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - keep the remaining scenes
                warnings.append(f"{scene.get('scene_id')}: {exc}")
        manifest = write_render_manifest(context.output, rendered)
        context.metadata["motion_manifest"] = rendered
        context.artifacts["motion_manifest"] = str(manifest)
        context.hashes["motion.render"] = digest_payload(
            {"rendered": len(rendered), "warnings": warnings}
        )
        if warnings:
            context.warnings.extend(warnings[:20])
        io.report(
            100,
            f"{len(rendered)} motion scene(s) rendered"
            + (f"; {len(warnings)} failed" if warnings else ""),
        )

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("motion_manifest")
        return (Path(path),) if path else ()
