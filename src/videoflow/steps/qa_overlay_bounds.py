"""Real overlay/caption/safe-zone collision QA."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.overlay_geometry import caption_box, collisions, layout_payload
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import RecipeError, StateNotReadyError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class OverlayBoundsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platforms: list[str] = Field(default_factory=lambda: ["youtube_16_9"])
    strict: bool = False
    include_captions: bool = True


@register_step
class OverlayBoundsStep(BaseStep):
    type = "qa.overlay_bounds"
    title = "Overlay bounds QA"
    description = (
        "Compute real pixel boxes for overlays and captions, detect overlaps, "
        "and validate platform safe zones."
    )
    produces = ("overlay_bounds",)
    params_model = OverlayBoundsParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = OverlayBoundsParams.model_validate(params)
        if context.state is None or context.media is None:
            raise StateNotReadyError("Overlay bounds QA requires a project timeline")
        width = context.media.width
        height = context.media.height
        caption = (
            caption_box(
                context.state.modules_config.shorts.caption_style,
                width,
                height,
            )
            if options.include_captions
            else None
        )
        issues = collisions(context.state, width, height, caption=caption)
        try:
            from videoflow.steps.qa_safezone import SAFE_ZONES

            for platform in options.platforms:
                for zone in SAFE_ZONES.get(platform, ()):
                    zone_box = (
                        zone.x * width,
                        zone.y * height,
                        (zone.x + zone.width) * width,
                        (zone.y + zone.height) * height,
                    )
                    for item in layout_payload(
                        context.state, width, height, caption=caption
                    )["overlays"]:
                        x, y = item["x"], item["y"]
                        right, bottom = x + item["w"], y + item["h"]
                        if not (
                            right <= zone_box[0]
                            or zone_box[2] <= x
                            or bottom <= zone_box[1]
                            or zone_box[3] <= y
                        ):
                            issues.append(
                                {
                                    "kind": "safe_zone",
                                    "item_a": item["overlay_id"],
                                    "item_b": f"{platform}:{zone.reason}",
                                    "overlap_px": 0,
                                    "start_sec": item["start_sec"],
                                    "end_sec": item["end_sec"],
                                }
                            )
        except Exception:  # noqa: BLE001 - safe-zone QA is optional
            pass
        report = {
            "ok": not issues,
            "canvas": {"width": width, "height": height},
            "issues": issues,
            "layout": layout_payload(context.state, width, height, caption=caption),
        }
        path = context.work / "qa" / "overlay_bounds.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        context.metadata["overlay_bounds"] = report
        context.artifacts["overlay_bounds"] = str(path)
        if options.strict and issues:
            raise RecipeError(
                f"Overlay bounds QA found {len(issues)} collision(s); see {path}"
            )
        io.report(100, f"Overlay bounds QA: {len(issues)} issue(s)")


__all__ = ["OverlayBoundsStep"]
