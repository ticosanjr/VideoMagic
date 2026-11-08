"""Content-cycle steps.

Implemented steps do real work. Planned steps are intentionally no-ops; the
runner marks them as skipped so a recipe can model the full workflow without
pretending a missing engine ran.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError
from videoflow.steps.base import BaseStep, EmptyParams, StepIO
from videoflow.steps.content_audio import (  # noqa: F401 - re-exported
    AudioMasterParams,
    AudioMasterStep,
    AudioQaParams,
    AudioQaStep,
)
from videoflow.steps.content_visual import (  # noqa: F401 - re-exported
    ColorGradeParams,
    ColorGradeStep,
    ThumbnailParams,
    ThumbnailStep,
    TitlesParams,
    TitlesStep,
)
from videoflow.steps.registry import register_step


class _BypassStep(BaseStep):
    status = "planned"
    icon = "○"
    color = "#71717a"
    params_model = EmptyParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        io.report(100, "Bypassed")


@register_step
class IdeaStep(_BypassStep):
    type = "content.idea"
    title = "Idea / angle"
    description = "Planned: topic, hook, audience, and angle selection."
    icon = "✦"


@register_step
class ResearchStep(_BypassStep):
    type = "content.research"
    title = "Research / references"
    description = "Planned: trend, keyword, competitor, and source research."
    icon = "⌕"


@register_step
class ScriptStep(_BypassStep):
    type = "content.script"
    title = "Script / outline"
    description = "Planned: outline, script, hook variants, and CTA."
    icon = "✎"


@register_step
class StoryboardStep(BaseStep):
    type = "storyboard.plan"
    title = "Storyboard / shot list"
    description = "Write a JSON storyboard from the validated timeline and transcript."
    status = "available"
    icon = "▤"
    color = "#22c55e"
    requires = ("edit.timeline",)
    params_model = EmptyParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        if context.state is None:
            raise IngestError("Storyboard requires a validated timeline.")
        media = context.media
        fps = (media.fps_num / media.fps_den) if media is not None else 30.0
        state = context.state
        payload = {
            "ok": True,
            "duration_sec": round(
                max((clip.timeline_out_frame for clip in state.video_segments), default=0)
                / max(0.001, fps),
                3,
            ),
            "scenes": [
                {
                    "id": clip.clip_id,
                    "start_sec": round(clip.timeline_in_frame / fps, 3),
                    "end_sec": round(clip.timeline_out_frame / fps, 3),
                    "transition": clip.transition_out.type if clip.transition_out else None,
                    "keyframes": len(clip.transform.keyframes),
                }
                for clip in state.video_segments
            ],
            "captions": [
                {
                    "id": sentence.id,
                    "text": sentence.text,
                    "speaker": sentence.speaker,
                }
                for sentence in state.transcript
            ],
            "shorts": list(context.shorts),
            "broll_plan": context.metadata.get("broll_plan", {}),
        }
        context.output.mkdir(parents=True, exist_ok=True)
        target = context.output / "storyboard.json"
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        context.artifacts["storyboard"] = str(target)
        io.report(100, "Storyboard ready")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("storyboard")
        return (Path(path),) if path else ()


class AssetIndexParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_dir: str = ""
    tags: list[str] = Field(default_factory=list)


@register_step
class AssetIndexStep(BaseStep):
    type = "assets.index"
    title = "Index assets"
    description = "Scan a local folder into the asset library index."
    status = "available"
    icon = "▦"
    color = "#22c55e"
    params_model = AssetIndexParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = AssetIndexParams.model_validate(params)
        if not options.asset_dir:
            io.report(100, "Asset indexing skipped")
            return
        from videoflow.application.assets import scan_directory

        records = scan_directory(Path(options.asset_dir), tags=options.tags)
        target = context.output / "assets-index.json"
        target.write_text(
            json.dumps({"ok": True, "assets": records}, indent=2) + "\n",
            encoding="utf-8",
        )
        context.metadata["assets_index"] = records
        context.artifacts["assets_index"] = str(target)
        io.report(100, f"Indexed {len(records)} assets")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("assets_index")
        return (Path(path),) if path else ()






















@register_step
class PublishStep(_BypassStep):
    type = "publish.webhook"
    title = "Publish / webhook"
    description = "Planned: scheduled delivery and webhook publishing."
    icon = "↗"


class AnalyticsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csv_path: str = ""


@register_step
class AnalyticsStep(BaseStep):
    type = "analytics.import"
    title = "Analytics / feedback"
    description = "Import retention/CTR metrics from CSV into a normalized JSON report."
    status = "available"
    icon = "▥"
    color = "#22c55e"
    params_model = AnalyticsParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = AnalyticsParams.model_validate(params)
        rows: list[dict[str, str]] = []
        if options.csv_path:
            path = Path(options.csv_path).expanduser()
            if not path.is_file():
                raise IngestError(f"Analytics CSV does not exist: {path}")
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = [dict(row) for row in csv.DictReader(handle)]
        columns = sorted({key for row in rows for key in row})
        numeric: dict[str, float] = {}
        for column in columns:
            values: list[float] = []
            for row in rows:
                try:
                    values.append(float(str(row.get(column, "")).strip()))
                except ValueError:
                    continue
            if values and len(values) == len(rows):
                numeric[column] = round(sum(values) / len(values), 4)
        payload = {
            "ok": True,
            "source": options.csv_path,
            "row_count": len(rows),
            "columns": columns,
            "averages": numeric,
            "rows": rows[:500],
        }
        target = context.output / "analytics.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        context.artifacts["analytics"] = str(target)
        context.metadata["analytics"] = payload
        io.report(100, f"Imported {len(rows)} analytics row(s)")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("analytics")
        return (Path(path),) if path else ()


@register_step
class ReviewStep(BaseStep):
    type = "review.queue"
    title = "Review / approval"
    description = "Write a deterministic review checklist for the current run."
    status = "available"
    icon = "✓"
    color = "#22c55e"
    params_model = EmptyParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        state = context.state
        checks = [
            {
                "id": "timeline",
                "label": "Timeline has picture and dialogue",
                "ok": bool(state and state.video_segments and state.audio_segments),
            },
            {
                "id": "captions",
                "label": "Transcript is present",
                "ok": bool(context.transcript or (state and state.transcript)),
            },
            {
                "id": "shorts",
                "label": "At least one Short was selected",
                "ok": bool(context.shorts),
            },
            {
                "id": "thumbnail",
                "label": "Thumbnail candidate exists",
                "ok": "thumbnail" in context.artifacts,
            },
            {
                "id": "audio_master",
                "label": "Audio master exists",
                "ok": "audio_master" in context.artifacts,
            },
            {
                "id": "titles",
                "label": "Title plan exists",
                "ok": "titles" in context.artifacts,
            },
        ]
        payload = {
            "ok": True,
            "approved": False,
            "checks": checks,
            "pending": [check["id"] for check in checks if not check["ok"]],
        }
        target = context.output / "review.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        context.artifacts["review"] = str(target)
        context.metadata["review"] = payload
        io.report(100, f"{len(checks) - len(payload['pending'])}/{len(checks)} checks ready")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("review")
        return (Path(path),) if path else ()
