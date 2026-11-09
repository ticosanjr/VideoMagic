"""Delivery steps: metadata, thumbnails, publishing, analytics, and NLE QA."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from videoflow.application.deliverables import (
    select_thumbnail,
    thumbnail_metrics,
)
from videoflow.application.publishing import enqueue_publish
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class PublishQueueParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str = ""
    platform: str = "youtube"

class AnalyticsReviewParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_column: str = "duration_sec"
    retention_column: str = "retention"
    ctr_column: str = "ctr"

class ExperimentParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choose_best: bool = True

@register_step
class PublishQueueStep(BaseStep):
    type = "publish.queue"
    title = "Publish queue"
    description = "Enqueue rendered Shorts to a configured webhook target."
    status = "available"
    icon = "↗"
    color = "#22c55e"
    requires = ("shorts.render",)
    produces = ("publish_queue",)
    params_model = PublishQueueParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = PublishQueueParams.model_validate(params)
        if not options.target:
            io.report(100, "Publish skipped: no target configured")
            return
        queued = []
        for index, entry in enumerate(context.shorts):
            path = entry.get("path") if isinstance(entry, dict) else None
            if not path:
                continue
            try:
                queued.append(
                    enqueue_publish(
                        target_name=options.target,
                        asset_path=Path(str(path)),
                        title=str(entry.get("title") or f"Short {index + 1}"),
                        platform=options.platform,
                    )
                )
            except Exception as exc:
                context.warnings.append(f"Publish queue failed for Short {index}: {exc}")
        target = context.output / "delivery" / "publish-queue.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(queued, indent=2) + "\n", encoding="utf-8")
        context.artifacts["publish_queue"] = str(target)
        io.report(100, f"{len(queued)} Short(s) queued")

@register_step
class AnalyticsReviewStep(BaseStep):
    type = "analytics.review"
    title = "Analytics review"
    description = "Turn imported analytics into selection weights and recommendations."
    status = "available"
    icon = "▥"
    color = "#22c55e"
    params_model = AnalyticsReviewParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = AnalyticsReviewParams.model_validate(params)
        source = context.artifacts.get("analytics")
        rows: list[dict[str, Any]] = []
        if source and Path(source).is_file():
            try:
                rows = list(json.loads(Path(source).read_text(encoding="utf-8")).get("rows", []))
            except (OSError, ValueError):
                rows = []
        best_duration = 0.0
        if rows:
            durations = [
                float(row.get(options.duration_column, 0))
                for row in rows
                if str(row.get(options.duration_column, "")).replace(".", "", 1).isdigit()
            ]
            if durations:
                best_duration = sorted(durations)[len(durations) // 2]
        recommendations = {
            "sample_size": len(rows),
            "suggested_duration_sec": round(best_duration, 2),
            "weights": {
                "hook_strength": 1.2 if rows else 1.0,
                "payoff": 1.2 if rows else 1.0,
                "duration_fit": 1.5 if best_duration else 1.0,
            },
        }
        target = context.output / "delivery" / "analytics-review.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(recommendations, indent=2) + "\n", encoding="utf-8")
        context.artifacts["analytics_review"] = str(target)
        context.metadata["analytics_weights"] = recommendations["weights"]
        io.report(100, f"Analytics reviewed: {len(rows)} row(s)")

@register_step
class ExperimentEvaluateStep(BaseStep):
    type = "experiment.evaluate"
    title = "Evaluate experiment"
    description = "Pick the thumbnail variant with the best CTR."
    status = "available"
    icon = "⚖"
    color = "#22c55e"
    params_model = ExperimentParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        ExperimentParams.model_validate(params)
        metrics = thumbnail_metrics(context.output)
        winner = metrics[0] if metrics else None
        if winner and winner.get("name"):
            try:
                select_thumbnail(context.output, str(winner["name"]))
            except Exception as exc:
                context.warnings.append(f"Thumbnail winner selection failed: {exc}")
        payload = {"metrics": metrics, "winner": winner}
        target = context.output / "delivery" / "experiment.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        context.artifacts["experiment"] = str(target)
        io.report(100, "Experiment evaluated" if metrics else "No metrics yet")

