"""Content-cycle steps.

Implemented steps do real work. Planned steps are intentionally no-ops; the
runner marks them as skipped so a recipe can model the full workflow without
pretending a missing engine ran.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError
from videoflow.steps.base import BaseStep, EmptyParams, StepIO
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
class AudioMasterStep(_BypassStep):
    type = "audio.master"
    title = "Audio master"
    description = "Planned: EQ, denoise, compression, and loudness delivery."
    icon = "♫"
    color = "#a78bfa"


@register_step
class TitlesStep(_BypassStep):
    type = "titles.plan"
    title = "Titles / graphics"
    description = "Planned: lower thirds, titles, and motion graphics."
    icon = "T"


@register_step
class ThumbnailStep(BaseStep):
    type = "thumbnail.generate"
    title = "Thumbnail / cover"
    description = "Render a thumbnail frame from the source."
    status = "available"
    icon = "▣"
    color = "#22c55e"
    requires = ("ingest",)
    params_model = EmptyParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        if context.media is None:
            raise IngestError("Thumbnail requires ingested media.")
        duration = (
            context.media.duration_frames
            * context.media.fps_den
            / max(1, context.media.fps_num)
        )
        target = context.output / "thumbnails" / "thumbnail.png"
        FFmpegAdapter().render_thumbnail(
            Path(context.source),
            target,
            time_sec=max(0.0, duration / 2),
        )
        context.artifacts["thumbnail"] = str(target)
        io.report(100, "Thumbnail ready")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("thumbnail")
        return (Path(path),) if path else ()


@register_step
class PublishStep(_BypassStep):
    type = "publish.webhook"
    title = "Publish / webhook"
    description = "Planned: scheduled delivery and webhook publishing."
    icon = "↗"


@register_step
class AnalyticsStep(_BypassStep):
    type = "analytics.import"
    title = "Analytics / feedback"
    description = "Planned: retention, CTR, and variant feedback."
    icon = "▥"


@register_step
class ReviewStep(_BypassStep):
    type = "review.queue"
    title = "Review / approval"
    description = "Planned: comments, approvals, and version comparison."
    icon = "✓"
