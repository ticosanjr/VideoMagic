"""Delivery steps: metadata, thumbnails, publishing, analytics, and NLE QA."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.deliverables import (
    list_thumbnails,
)
from videoflow.application.short_metadata import generate_short_metadata
from videoflow.application.thumbnail import generate_short_thumbnail
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.delivery_common import _result
from videoflow.steps.registry import register_step


class MetadataPackParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: Literal["youtube", "tiktok", "instagram", "linkedin"] = "youtube"
    platforms: list[str] = Field(default_factory=list)
    tone: str = "engaging"
    hashtags: list[str] = Field(default_factory=list)

class ThumbnailPackParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variants: int = Field(default=1, ge=1, le=5)

@register_step
class MetadataPackStep(BaseStep):
    type = "metadata.pack"
    title = "Metadata pack"
    description = "Generate title, description, and hashtags for every Short."
    status = "available"
    icon = "≡"
    color = "#22c55e"
    requires = ("shorts.select",)
    produces = ("metadata_pack",)
    params_model = MetadataPackParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = MetadataPackParams.model_validate(params)
        result = _result(context)
        entries = []
        for index, _ in enumerate(context.shorts):
            try:
                metadata = generate_short_metadata(
                    output=context.output,
                    index=index,
                    result=result,
                    platform=options.platform,
                    tone=options.tone,
                    extra_hashtags=tuple(options.hashtags),
                    ai=io.ai,
                )
                entries.append(metadata)
            except Exception as exc:
                context.warnings.append(f"Metadata failed for Short {index}: {exc}")
        target = context.output / "delivery" / "metadata.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
        context.artifacts["metadata_pack"] = str(target)
        platforms = options.platforms or [options.platform]
        social: list[dict[str, object]] = []
        for index, _ in enumerate(context.shorts):
            per_platform: dict[str, object] = {}
            for platform in platforms:
                try:
                    per_platform[platform] = generate_short_metadata(
                        output=context.output,
                        index=index,
                        result=result,
                        platform=platform,
                        tone=options.tone,
                        extra_hashtags=tuple(options.hashtags),
                    )
                except Exception as exc:
                    context.warnings.append(
                        f"Social metadata failed for Short {index} on {platform}: {exc}"
                    )
            if per_platform:
                social.append({"short_index": index, "platforms": per_platform})
        social_target = context.output / "delivery" / "social_descriptions.json"
        social_target.write_text(
            json.dumps(
                {
                    "ok": True,
                    "platforms": platforms,
                    "shorts": social,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        context.artifacts["social_descriptions"] = str(social_target)
        io.report(100, f"{len(entries)} metadata record(s)")

@register_step
class ThumbnailPackStep(BaseStep):
    type = "thumbnail.pack"
    title = "Thumbnail pack"
    description = "Render one or more thumbnails per Short for A/B selection."
    status = "available"
    icon = "▣"
    color = "#22c55e"
    requires = ("shorts.render",)
    produces = ("thumbnail_pack",)
    params_model = ThumbnailPackParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ThumbnailPackParams.model_validate(params)
        result = _result(context)
        directory = context.output / "thumbnails"
        directory.mkdir(parents=True, exist_ok=True)
        fractions = [0.15, 0.35, 0.55, 0.75, 0.9]
        for index, entry in enumerate(context.shorts):
            duration = float(entry.get("duration_sec") or 0.0) if isinstance(entry, dict) else 0.0
            for variant in range(options.variants):
                try:
                    payload = generate_short_thumbnail(
                        output=context.output,
                        index=index,
                        result=result,
                        time_sec=max(0.2, duration * fractions[variant % len(fractions)]),
                        caption_style={"font_size": 60 + variant * 8},
                    )
                    source = Path(str(payload["path"]))
                    target = directory / f"variant-{index + 1}-{variant + 1}.png"
                    shutil.copy2(source, target)
                except Exception as exc:
                    context.warnings.append(f"Thumbnail failed for Short {index}: {exc}")
        listing = list_thumbnails(context.output)
        context.metadata["thumbnail_pack"] = listing
        io.report(100, f"{len(listing['variants'])} thumbnail variant(s)")

