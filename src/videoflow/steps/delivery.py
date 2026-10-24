"""Delivery steps: metadata, thumbnails, publishing, analytics, and NLE QA."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.deliverables import list_thumbnails, thumbnail_metrics
from videoflow.application.nle_validation import validate_nle_exports
from videoflow.application.publishing import enqueue_publish
from videoflow.application.short_metadata import generate_short_metadata
from videoflow.application.thumbnail import generate_short_thumbnail
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


def _result(context: PipelineContext) -> dict[str, Any]:
    return {"ok": True, "shorts": list(context.shorts), "artifacts": dict(context.artifacts)}


class MetadataPackParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: Literal["youtube", "tiktok", "instagram", "linkedin"] = "youtube"
    tone: str = "engaging"
    hashtags: list[str] = Field(default_factory=list)


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
                )
                entries.append(metadata)
            except Exception as exc:
                context.warnings.append(f"Metadata failed for Short {index}: {exc}")
        target = context.output / "delivery" / "metadata.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
        context.artifacts["metadata_pack"] = str(target)
        io.report(100, f"{len(entries)} metadata record(s)")


class ThumbnailPackParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variants: int = Field(default=1, ge=1, le=5)


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


class PublishQueueParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str = ""
    platform: str = "youtube"


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


class AnalyticsReviewParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_column: str = "duration_sec"
    retention_column: str = "retention"
    ctr_column: str = "ctr"


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


class ExperimentParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choose_best: bool = True


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
        payload = {"metrics": metrics, "winner": winner}
        target = context.output / "delivery" / "experiment.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        context.artifacts["experiment"] = str(target)
        io.report(100, "Experiment evaluated" if metrics else "No metrics yet")


class ChaptersParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_chapters: int = Field(default=12, ge=1, le=50)


@register_step
class ChaptersStep(BaseStep):
    type = "chapters.plan"
    title = "Chapter markers"
    description = "Create chapter markers from the transcript and timeline."
    status = "available"
    icon = "⌁"
    color = "#22c55e"
    requires = ("transcribe",)
    produces = ("chapters",)
    params_model = ChaptersParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ChaptersParams.model_validate(params)
        sentences = context.transcript or (context.state.transcript if context.state else [])
        rate = context.media.audio_sample_rate if context.media is not None else 48000
        chapters = []
        step = max(1, len(sentences) // options.max_chapters)
        for index in range(0, len(sentences), step):
            sentence = sentences[index]
            chapters.append(
                {
                    "title": sentence.text[:60],
                    "start_sec": round(sentence.start_sample / max(1, rate), 3),
                }
            )
        target = context.output / "chapters.json"
        target.write_text(json.dumps({"chapters": chapters}, indent=2) + "\n", encoding="utf-8")
        context.artifacts["chapters"] = str(target)
        io.report(100, f"{len(chapters)} chapter(s)")


class NleQaParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    directory: str = ""


@register_step
class NleQaStep(BaseStep):
    type = "nle.qa"
    title = "NLE QA"
    description = "Validate exported NLE files and write a QA report."
    status = "available"
    icon = "✓"
    color = "#22c55e"
    requires = ("export.nle",)
    produces = ("nle_qa",)
    params_model = NleQaParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = NleQaParams.model_validate(params)
        directory = (
            Path(options.directory).expanduser()
            if options.directory
            else context.output / "exports"
        )
        report = validate_nle_exports(directory)
        target = context.output / "exports" / "qa-report.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        context.artifacts["nle_qa"] = str(target)
        io.report(100, "NLE QA complete")
