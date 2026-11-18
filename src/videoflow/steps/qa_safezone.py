"""Geometric safe-zone QA for Reels, TikTok, Shorts, and YouTube."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.headless import SafeZoneBox, SafeZoneCollision, SafeZoneReport
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step

SAFE_ZONES: dict[str, tuple[SafeZoneBox, ...]] = {
    "reels": (
        SafeZoneBox(platform="reels", x=0.0, y=0.82, width=1.0, height=0.18, reason="bottom UI"),
        SafeZoneBox(
            platform="reels", x=0.86, y=0.0, width=0.14, height=1.0, reason="right action rail"
        ),
        SafeZoneBox(platform="reels", x=0.0, y=0.0, width=1.0, height=0.08, reason="top chrome"),
    ),
    "tiktok": (
        SafeZoneBox(platform="tiktok", x=0.0, y=0.80, width=1.0, height=0.20, reason="bottom UI"),
        SafeZoneBox(
            platform="tiktok", x=0.84, y=0.0, width=0.16, height=1.0, reason="right action rail"
        ),
        SafeZoneBox(platform="tiktok", x=0.0, y=0.0, width=1.0, height=0.10, reason="top chrome"),
    ),
    "shorts": (
        SafeZoneBox(platform="shorts", x=0.0, y=0.84, width=1.0, height=0.16, reason="bottom UI"),
        SafeZoneBox(
            platform="shorts", x=0.86, y=0.0, width=0.14, height=1.0, reason="right action rail"
        ),
        SafeZoneBox(platform="shorts", x=0.0, y=0.0, width=1.0, height=0.08, reason="top chrome"),
    ),
    "youtube": (
        SafeZoneBox(
            platform="youtube", x=0.0, y=0.88, width=1.0, height=0.12, reason="progress bar"
        ),
    ),
    "youtube_16_9": (
        SafeZoneBox(
            platform="youtube_16_9", x=0.0, y=0.90, width=1.0, height=0.10, reason="progress bar"
        ),
        SafeZoneBox(
            platform="youtube_16_9", x=0.0, y=0.0, width=1.0, height=0.06, reason="top chrome"
        ),
    ),
    "feed_4_5": (
        SafeZoneBox(
            platform="feed_4_5", x=0.0, y=0.86, width=1.0, height=0.14, reason="caption band"
        ),
        SafeZoneBox(
            platform="feed_4_5", x=0.0, y=0.0, width=1.0, height=0.07, reason="top chrome"
        ),
    ),
}


class SafeZoneParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platforms: list[str] = Field(default_factory=lambda: ["reels", "tiktok", "shorts"])
    strict: bool = False
    include_captions: bool = True
    include_overlays: bool = True
    caption_box: list[float] = Field(default_factory=lambda: [0.05, 0.72, 0.90, 0.14])


def _box(x: float, y: float, width: float, height: float) -> tuple[float, float, float, float]:
    return x, y, x + width, y + height


def _overlaps(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    return not (
        left[2] <= right[0] or right[2] <= left[0] or left[3] <= right[1] or right[3] <= left[1]
    )


def _collision(
    platform: str,
    element_id: str,
    element_kind: str,
    element: tuple[float, float, float, float],
    start_sec: float,
    end_sec: float,
) -> SafeZoneCollision | None:
    for zone in SAFE_ZONES.get(platform, ()):
        if _overlaps(element, _box(zone.x, zone.y, zone.width, zone.height)):
            return SafeZoneCollision(
                platform=platform,
                element_id=element_id,
                element_kind=element_kind,
                start_sec=start_sec,
                end_sec=end_sec,
                bbox=list(element),
                safe_zone=zone,
                message=f"{element_kind} enters {platform} {zone.reason}",
            )
    return None


@register_step
class SafeZoneStep(BaseStep):
    type = "qa.safezone"
    status = "available"
    icon = "▣"
    color = "#22c55e"
    title = "Safe-zone QA"
    description = "Check captions, titles, and overlays against platform UI masks."
    requires = ()
    produces = ("safezone_report",)
    params_model = SafeZoneParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = SafeZoneParams.model_validate(params)
        collisions: list[SafeZoneCollision] = []
        platforms = [item for item in options.platforms if item in SAFE_ZONES]
        io.report(10, "Checking platform safe zones")
        if options.include_overlays and context.state is not None and context.media is not None:
            from videoflow.application.overlay_geometry import layout_for

            for item in layout_for(context.state, context.media.width, context.media.height):
                element = item.box.normalised(context.media.width, context.media.height)
                for platform in platforms:
                    found = _collision(
                        platform,
                        item.overlay_id,
                        "overlay",
                        element,
                        item.start_sec,
                        item.end_sec,
                    )
                    if found:
                        collisions.append(found)
        if options.include_captions and context.short_captions:
            caption = options.caption_box
            element = _box(caption[0], caption[1], caption[2], caption[3])
            for platform in platforms:
                found = _collision(platform, "captions", "captions", element, 0.0, 0.0)
                if found:
                    collisions.append(found)
        report = SafeZoneReport(
            platforms=platforms,
            collisions=collisions,
            passed=not collisions,
        )
        path = context.work / "qa" / "safezone.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        context.metadata["safezone_report"] = report.model_dump(mode="json")
        context.artifacts["safezone_report"] = str(path)
        context.hashes["safezone"] = report.model_dump_json()
        if options.strict and collisions:
            from videoflow.domain.errors import RecipeError

            raise RecipeError(f"Safe-zone QA found {len(collisions)} collision(s); see {path}")
        io.report(100, f"Safe-zone QA: {len(collisions)} collision(s)")
