"""Short placeholder previews for the unit-storyboard review.

The full motion render happens after assets are assigned. This step renders four
representative placeholder scenes earlier so the human can approve composition,
palette, and typography before the expensive media pass.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.files import read_json_or
from videoflow.application.motion import build_scenes, render_scene
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step

_PREFERRED_LAYOUTS = ("full_screen", "lower_third", "presenter_split", "presenter_visual")


class StoryboardPreviewParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    units_path: str = Field(default="storyboard/units.json", max_length=2000)
    style_path: str = Field(default="style/style-guide.json", max_length=2000)
    output_dir: str = Field(default="exports/previews", max_length=2000)
    duration_sec: float = Field(default=60.0, ge=3.0, le=180.0)
    width: int = Field(default=1920, ge=16, le=7680)
    height: int = Field(default=1080, ge=16, le=4320)
    fps: int = Field(default=30, ge=1, le=120)
    render: bool = True
    draft_scale: float = Field(default=1.0, ge=0.1, le=1.0)


def _units(payload: Any) -> list[dict[str, Any]]:
    items = payload.get("units") if isinstance(payload, dict) else payload
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _select(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used: set[int] = set()
    for layout in _PREFERRED_LAYOUTS:
        for index, unit in enumerate(units):
            if index in used or str(unit.get("layout") or "") != layout:
                continue
            selected.append(unit)
            used.add(index)
            break
    for index, unit in enumerate(units):
        if len(selected) >= len(_PREFERRED_LAYOUTS):
            break
        if index not in used:
            selected.append(unit)
            used.add(index)
    return selected[: len(_PREFERRED_LAYOUTS)]


@register_step
class StoryboardPreviewStep(BaseStep):
    type = "storyboard.preview"
    title = "Preview placeholders"
    description = (
        "Render four representative placeholder clips from the unit storyboard "
        "and style guide for the composition review before asset harvesting."
    )
    status = "available"
    icon = "▣"
    color = "#ec4899"
    produces = ("storyboard_previews",)
    params_model = StoryboardPreviewParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = StoryboardPreviewParams.model_validate(params)
        units = _units(read_json_or(context.output / options.units_path, {}))
        style_payload = read_json_or(context.output / options.style_path, {})
        style = style_payload if isinstance(style_payload, dict) else {}
        selected = _select(units)
        scenes = build_scenes(
            selected,
            style=style,
            assets={},
            width=options.width,
            height=options.height,
            fps=options.fps,
            max_scenes=len(_PREFERRED_LAYOUTS),
        )
        output_dir = context.output / options.output_dir
        manifest: list[dict[str, Any]] = []
        for index, scene in enumerate(scenes, start=1):
            scene["scene_id"] = f"PREVIEW-{index:02d}"
            scene["duration_sec"] = min(
                options.duration_sec,
                max(3.0, float(scene.get("duration_sec") or options.duration_sec)),
            )
            entry = {
                "scene_id": scene["scene_id"],
                "unit_id": scene.get("unit_id"),
                "title": scene.get("title"),
                "layout": scene.get("layout"),
                "duration_sec": scene["duration_sec"],
                "path": "",
            }
            if options.render:
                try:
                    entry["path"] = str(
                        render_scene(scene, output_dir, draft_scale=options.draft_scale)
                    )
                except Exception as exc:  # noqa: BLE001 - review can use the manifest
                    context.warnings.append(f"Preview render failed: {exc}")
                    io.emit("warning", f"Preview render failed: {exc}", module="storyboard.preview")
            manifest.append(entry)
        target = context.output / "storyboard" / "previews.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {"previews": manifest, "count": len(manifest)},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        context.metadata["storyboard_previews"] = manifest
        context.artifacts["storyboard_previews"] = str(target)
        context.hashes["storyboard.preview"] = digest_payload(
            {"count": len(manifest), "render": options.render}
        )
        rendered = sum(1 for item in manifest if item["path"])
        io.report(100, f"{rendered}/{len(manifest)} preview clip(s) ready")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        paths: list[Path] = []
        target = context.artifacts.get("storyboard_previews")
        if target:
            paths.append(Path(target))
        for item in context.metadata.get("storyboard_previews", []):
            if isinstance(item, dict) and item.get("path"):
                paths.append(Path(str(item["path"])))
        return tuple(paths)
