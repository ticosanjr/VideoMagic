"""Plan local B-roll overlays for selected Shorts.

The planner matches local asset filenames against the selected clip title and
stores a small overlay plan in the pipeline context. The render step applies the
plan as a full-frame cutaway.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class BrollParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_dir: str = ""
    max_per_short: int = Field(default=1, ge=1, le=5)
    start_fraction: float = Field(default=0.2, ge=0.0, le=0.9)
    duration_sec: float = Field(default=2.0, gt=0.0, le=30.0)


@register_step
class BrollStep(BaseStep):
    type = "broll.plan"
    title = "B-roll plan"
    description = "Assign local stock assets to selected Shorts as full-frame cutaways."
    requires = ("shorts.select",)
    produces = ("broll_plan",)
    params_model = BrollParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = BrollParams.model_validate(params)
        if not context.selected_shorts:
            io.report(100, "No Shorts selected")
            return
        if not options.asset_dir:
            context.metadata["broll_plan"] = {}
            io.report(100, "B-roll disabled")
            return
        directory = Path(options.asset_dir).expanduser()
        if not directory.is_dir():
            raise IngestError(f"B-roll directory does not exist: {directory}")
        assets = [
            path
            for path in sorted(directory.iterdir())
            if path.is_file() and path.suffix.casefold() in VIDEO_SUFFIXES | IMAGE_SUFFIXES
        ]
        if not assets:
            context.metadata["broll_plan"] = {}
            context.warnings.append("B-roll skipped: no media files in the asset directory")
            io.report(100, "No B-roll assets")
            return
        plan: dict[str, list[dict[str, Any]]] = {}
        used: set[str] = set()
        total = max(1, len(context.selected_shorts))
        for index, clip in enumerate(context.selected_shorts):
            words = {token for token in clip.title.casefold().replace("_", " ").split() if token}
            ranked = sorted(
                assets,
                key=lambda asset: (
                    -sum(1 for word in words if word in asset.stem.casefold()),
                    asset.name.casefold(),
                ),
            )
            chosen = [asset for asset in ranked if asset.name not in used][: options.max_per_short]
            if not chosen:
                chosen = ranked[: options.max_per_short]
            entries = []
            for offset, asset in enumerate(chosen):
                used.add(asset.name)
                entries.append(
                    {
                        "path": str(asset),
                        "start_sec": round(
                            max(
                                0.0,
                                clip.duration_samples
                                / (context.media.audio_sample_rate if context.media else 48000)
                                * options.start_fraction,
                            )
                            + offset * options.duration_sec,
                            3,
                        ),
                        "duration_sec": options.duration_sec,
                    }
                )
            plan[clip.title] = entries
            io.report(int((index + 1) / total * 100), f"Planned B-roll {index + 1}/{total}")
        context.metadata["broll_plan"] = plan
        (context.output / "broll.json").write_text(
            json.dumps({"ok": True, "shorts": plan}, indent=2) + "\n",
            encoding="utf-8",
        )
        context.hashes["broll"] = digest_payload(plan)
        io.report(100, f"{sum(len(items) for items in plan.values())} B-roll overlays planned")
