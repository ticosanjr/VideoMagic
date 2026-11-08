"""Asset intelligence: shots, semantic matching, beats, and SFX planning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.video_analysis import detect_scene_changes, scene_intervals
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import require_media
from videoflow.steps.registry import register_step


class ShotsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold: float = Field(default=0.35, ge=0.05, le=0.95)
    thumbnails: bool = True

@register_step
class ShotsStep(BaseStep):
    type = "assets.shots"
    title = "Detect shots"
    description = "Detect scene cuts and extract one thumbnail per shot."
    status = "available"
    icon = "▦"
    color = "#22c55e"
    requires = ("ingest",)
    produces = ("shots",)
    params_model = ShotsParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ShotsParams.model_validate(params)
        media = require_media(context)
        spans = scene_intervals(
            detect_scene_changes(Path(context.source), threshold=options.threshold),
            sample_rate=media.audio_sample_rate,
        )
        directory = context.output / "shots"
        directory.mkdir(parents=True, exist_ok=True)
        shots: list[dict[str, Any]] = []
        for index, (start, end) in enumerate(spans or [(0, context.duration_samples())]):
            entry: dict[str, Any] = {
                "id": f"shot-{index + 1}",
                "start_sample": start,
                "end_sample": end,
            }
            if options.thumbnails:
                target = directory / f"{entry['id']}.png"
                try:
                    FFmpegAdapter().render_thumbnail(
                        Path(context.source),
                        target,
                        time_sec=((start + end) / 2) / max(1, media.audio_sample_rate),
                    )
                    entry["thumbnail"] = str(target)
                except Exception as exc:
                    context.warnings.append(f"Shot thumbnail failed: {exc}")
            shots.append(entry)
        target = context.output / "shots" / "shots.json"
        target.write_text(json.dumps({"shots": shots}, indent=2) + "\n", encoding="utf-8")
        context.artifacts["shots"] = str(target)
        context.metadata["scenes"] = shots
        io.report(100, f"{len(shots)} shot(s) detected")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("shots")
        return (Path(path),) if path else ()
