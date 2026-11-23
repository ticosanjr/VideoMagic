"""Code-driven scene generation, headless rendering, assembly, and master export."""

from __future__ import annotations

import contextlib
import json
import shutil
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.export_names import unique_path
from videoflow.application.files import read_json_or
from videoflow.application.motion import build_scenes
from videoflow.application.scene_web import (
    concatenate,
    mux_master,
    render_html_scene,
    render_scene_ffmpeg,
    write_manifest,
    write_scene_html,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ExportError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


def _assignments(context: PipelineContext, path: str) -> dict[str, list[dict[str, Any]]]:
    payload = read_json_or(context.output / path, {})
    items = payload.get("assignments", []) if isinstance(payload, dict) else payload
    assets: dict[str, list[dict[str, Any]]] = {}
    for item in items if isinstance(items, list) else []:
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
    return assets


class SceneCodegenParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    units_path: str = Field(default="storyboard/units.json", max_length=2000)
    style_path: str = Field(default="style/style-guide.json", max_length=2000)
    assignments_path: str = Field(default="assets/assignments.json", max_length=2000)
    engine: Literal["html", "three", "ffmpeg"] = "html"
    title_style: Literal["lower_third", "center"] = "lower_third"
    three_js_path: str = Field(default="", max_length=2000)
    width: int = Field(default=1920, ge=16, le=7680)
    height: int = Field(default=1080, ge=16, le=4320)
    fps: int = Field(default=30, ge=1, le=60)
    max_scenes: int = Field(default=400, ge=1, le=1000)


@register_step
class SceneCodegenStep(BaseStep):
    type = "scene.codegen"
    title = "Scene codegen"
    description = (
        "Build a 2.5D scene graph and HTML/CSS scene documents from timed units, "
        "style, and approved assets."
    )
    status = "available"
    icon = "</>"
    color = "#38bdf8"
    params_model = SceneCodegenParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = SceneCodegenParams.model_validate(params)
        units_payload = read_json_or(context.output / options.units_path, {})
        style_payload = read_json_or(context.output / options.style_path, {})
        units = units_payload.get("units", []) if isinstance(units_payload, dict) else units_payload
        style = style_payload if isinstance(style_payload, dict) else {}
        assets = _assignments(context, options.assignments_path)
        scenes = build_scenes(
            units if isinstance(units, list) else [],
            style=style,
            assets=assets,
            width=options.width,
            height=options.height,
            fps=options.fps,
            max_scenes=options.max_scenes,
        )
        if not scenes:
            raise ExportError("Scene codegen found no timed units.")
        code_dir = context.output / "motion" / "code"
        code_dir.mkdir(parents=True, exist_ok=True)
        three_js = False
        if options.three_js_path:
            source = Path(options.three_js_path).expanduser()
            if source.is_file():
                shutil.copy2(source, code_dir / "three.module.js")
                three_js = True
        for scene in scenes:
            scene["engine"] = options.engine
            write_scene_html(
                scene,
                code_dir,
                title_style=options.title_style,
                three_js=three_js,
            )
        target = context.output / "motion" / "scenes.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"scenes": scenes, "count": len(scenes)}, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest = write_manifest(code_dir, scenes)
        context.metadata["motion_scenes"] = scenes
        context.artifacts["motion_scenes"] = str(target)
        context.artifacts["scene_code"] = str(code_dir)
        context.artifacts["scene_code_manifest"] = str(manifest)
        context.hashes["scene.codegen"] = digest_payload(
            {"scenes": len(scenes), "engine": options.engine}
        )
        io.report(100, f"{len(scenes)} scene document(s) generated")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("motion_scenes", "scene_code")
            if context.artifacts.get(key)
        )


class SceneRenderParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: Literal["auto", "playwright", "ffmpeg"] = "auto"
    max_scenes: int = Field(default=400, ge=1, le=1000)
    fps: int = Field(default=30, ge=1, le=60)
    width: int = Field(default=1920, ge=16, le=7680)
    height: int = Field(default=1080, ge=16, le=4320)
    draft_scale: float = Field(default=1.0, gt=0.0, le=1.0)
    timeout: float = Field(default=600.0, ge=30.0, le=3600.0)


@register_step
class SceneRenderStep(BaseStep):
    type = "scene.render"
    title = "Render scenes"
    description = (
        "Render HTML/CSS scenes with a headless browser when available, then "
        "fall back to the built-in FFmpeg scene renderer."
    )
    status = "available"
    icon = "▶"
    color = "#38bdf8"
    requires = ("scene.codegen",)
    params_model = SceneRenderParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = SceneRenderParams.model_validate(params)
        payload = read_json_or(context.output / "motion" / "scenes.json", {})
        scenes = payload.get("scenes", []) if isinstance(payload, dict) else []
        if not isinstance(scenes, list) or not scenes:
            raise ExportError("Scene render requires generated scenes.")
        engine = options.engine
        if engine == "auto":
            try:
                import playwright  # noqa: F401

                engine = "playwright"
            except Exception:
                engine = "ffmpeg"
        rendered: list[dict[str, Any]] = []
        warnings: list[str] = []
        total = min(len(scenes), options.max_scenes)
        for index, scene in enumerate(scenes[:total], start=1):
            if not isinstance(scene, dict):
                continue
            scene_id = str(scene.get("scene_id") or f"SCENE-{index:04d}")
            duration = max(0.5, float(scene.get("duration_sec") or 5.0))
            target = context.output / "motion" / "rendered" / f"{scene_id}.mp4"
            io.report(
                int((index - 1) / max(1, total) * 100),
                f"Rendering scene {index}/{total}",
            )
            rendered_path: Path | None = None
            if engine == "playwright":
                html_path = context.output / "motion" / "code" / f"{scene_id}.html"
                if html_path.is_file():
                    try:
                        rendered_path = render_html_scene(
                            context.output / "motion" / "code",
                            f"{scene_id}.html",
                            target,
                            duration_sec=duration,
                            fps=options.fps,
                            width=options.width,
                            height=options.height,
                            draft_scale=options.draft_scale,
                            timeout=options.timeout,
                        )
                    except Exception as exc:  # noqa: BLE001 - renderer fallback
                        warnings.append(f"{scene_id}: headless render fallback: {exc}")
            if rendered_path is None:
                try:
                    rendered_path = render_scene_ffmpeg(
                        scene,
                        context.output / "motion" / "rendered",
                        draft_scale=options.draft_scale,
                    )
                except Exception as exc:  # noqa: BLE001 - keep the remaining scenes
                    warnings.append(f"{scene_id}: {exc}")
                    continue
            rendered.append(
                {
                    "scene_id": scene_id,
                    "unit_id": scene.get("unit_id"),
                    "title": scene.get("title"),
                    "path": str(rendered_path),
                    "start_sec": float(scene.get("start_sec") or 0.0),
                    "duration_sec": duration,
                }
            )
        if not rendered:
            raise ExportError("No scene rendered successfully.")
        manifest = write_manifest(context.output / "motion", rendered)
        context.metadata["motion_manifest"] = rendered
        context.artifacts["motion_manifest"] = str(manifest)
        if warnings:
            context.warnings.extend(warnings[:20])
        context.hashes["scene.render"] = digest_payload(
            {"rendered": len(rendered), "engine": engine}
        )
        io.report(
            100,
            f"{len(rendered)} scene(s) rendered with {engine}"
            + (f"; {len(warnings)} warning(s)" if warnings else ""),
        )

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("motion_manifest")
        return (Path(path),) if path else ()


class SceneAssembleParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_path: str = Field(default="exports/draft.mp4", max_length=2000)
    burn_subtitles: bool = True
    allow_silent: bool = False
    preset: Literal["ultrafast", "fast"] = "ultrafast"


@register_step
class SceneAssembleStep(BaseStep):
    type = "scene.assemble"
    title = "Assemble scenes"
    description = (
        "Concatenate the rendered scenes, burn titles/captions, and mux the "
        "approved final audio into a draft master."
    )
    status = "available"
    icon = "⏵"
    color = "#38bdf8"
    requires = ("scene.render", "audio.mix")
    params_model = SceneAssembleParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = SceneAssembleParams.model_validate(params)
        payload = read_json_or(context.output / "motion" / "render-manifest.json", {})
        scenes = payload.get("scenes", []) if isinstance(payload, dict) else []
        paths = [
            Path(str(item.get("path")))
            for item in scenes
            if isinstance(item, dict) and Path(str(item.get("path") or "")).is_file()
        ]
        paths.sort(
            key=lambda path: next(
                (
                    float(item.get("start_sec") or 0.0)
                    for item in scenes
                    if isinstance(item, dict) and str(item.get("path")) == str(path)
                ),
                0.0,
            )
        )
        if not paths:
            raise ExportError("Scene assembly found no rendered clips.")
        audio_value = context.artifacts.get("audio_mix") or context.artifacts.get("audio_master")
        audio = Path(audio_value) if audio_value else context.output / "audio" / "final.wav"
        if not audio.is_file() and not options.allow_silent:
            raise ExportError("Scene assembly needs the final audio mix.")
        joined = context.output / "motion" / "assembly.mp4"
        concatenate(paths, joined)
        target = context.output / options.output_path
        subtitles = None
        if options.burn_subtitles:
            for name in ("subtitles.ass", "titles.ass"):
                candidate = context.output / name
                if candidate.is_file():
                    subtitles = candidate
                    break
        mux_master(joined, audio, target, subtitles=subtitles)
        with contextlib.suppress(OSError):
            joined.unlink()
        context.artifacts["video_draft"] = str(target)
        context.hashes["scene.assemble"] = digest_payload(
            {"scenes": len(paths), "audio": str(audio)}
        )
        io.report(100, f"Draft assembled: {target.name}")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("video_draft")
        return (Path(path),) if path else ()


class ExportMasterParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subdir: str = Field(default="exports", max_length=120)
    filename: str = Field(default="master.mp4", min_length=1, max_length=200)


@register_step
class ExportMasterStep(BaseStep):
    type = "export.master"
    title = "Export master"
    description = "Copy the approved draft to the final master and write its report."
    status = "available"
    icon = "✓"
    color = "#fb7185"
    requires = ("scene.assemble",)
    params_model = ExportMasterParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ExportMasterParams.model_validate(params)
        source = context.artifacts.get("video_draft") or context.artifacts.get("video")
        if not source or not Path(source).is_file():
            raise ExportError("Master export requires the approved draft video.")
        directory = context.output / options.subdir
        directory.mkdir(parents=True, exist_ok=True)
        target = unique_path(directory, Path(options.filename).name)
        shutil.copy2(source, target)
        report = {
            "source": str(source),
            "master": str(target),
            "bytes": target.stat().st_size,
            "duration_sec": context.metadata.get("narration_duration_sec", 0.0),
            "audio_qa": context.metadata.get("audio_qa", {}),
            "vision_qa": context.metadata.get("vision_qa", {}),
        }
        report_path = directory / f"{target.stem}.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        context.artifacts["video"] = str(target)
        context.artifacts["video_master"] = str(target)
        context.artifacts["master_report"] = str(report_path)
        context.hashes["export.master"] = digest_payload(report)
        io.report(100, f"Master ready: {target.name}")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("video_master", "master_report")
            if context.artifacts.get(key)
        )


__all__ = [
    "ExportMasterParams",
    "ExportMasterStep",
    "SceneAssembleParams",
    "SceneAssembleStep",
    "SceneCodegenParams",
    "SceneCodegenStep",
    "SceneRenderParams",
    "SceneRenderStep",
]
