"""Generate ASS caption files for selected Shorts before rendering."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.shorts import (
    build_ass,
    build_ass_lines,
    caption_lines,
    sentence_events,
    slugify,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.config import CaptionStyle
from videoflow.exporters.common import write_text
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload, require_media
from videoflow.steps.registry import register_step


class CaptionsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    caption_style: CaptionStyle = Field(default_factory=CaptionStyle)


@register_step
class CaptionsStep(BaseStep):
    type = "shorts.captions"
    title = "Shorts captions"
    description = (
        "Build karaoke/ASS caption files for every selected Short without rendering video."
    )
    requires = ("shorts.select",)
    produces = ("short_captions",)
    params_model = CaptionsParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = CaptionsParams.model_validate(params)
        media = require_media(context)
        if not options.enabled:
            context.short_captions = {}
            context.metadata["captions_disabled"] = True
            io.report(100, "Caption generation disabled")
            return
        if not context.selected_shorts:
            context.short_captions = {}
            io.report(100, "No Shorts selected")
            return
        discard = set(context.discard_sentence_ids)
        kept = [item for item in context.transcript if item.id not in discard]
        directory = context.output / "shorts"
        directory.mkdir(parents=True, exist_ok=True)
        captions: dict[str, str] = {}
        total = max(1, len(context.selected_shorts))
        for index, clip in enumerate(context.selected_shorts, start=1):
            io.check_cancel()
            entry = context.shorts[index - 1] if index <= len(context.shorts) else {}
            width = int(entry.get("width", 1080))
            height = int(entry.get("height", 1920))
            slug = slugify(clip.title, index)
            lines = caption_lines(
                kept,
                clip.pieces,
                sample_rate=media.audio_sample_rate,
                word_timing=options.caption_style.word_timing,
                warnings=context.warnings,
            )
            if lines:
                ass_path = directory / f"{slug}.ass"
                write_text(
                    ass_path,
                    build_ass_lines(
                        lines,
                        style=options.caption_style,
                        width=width,
                        height=height,
                    ),
                )
            else:
                events = sentence_events(
                    kept, clip.pieces, sample_rate=media.audio_sample_rate
                )
                if not events:
                    io.report(int(index / total * 100), f"Skipped captions {index}/{total}")
                    continue
                ass_path = directory / f"{slug}.ass"
                write_text(
                    ass_path,
                    build_ass(
                        events,
                        style=options.caption_style,
                        width=width,
                        height=height,
                    ),
                )
            captions[clip.title] = str(ass_path)
            if index <= len(context.shorts):
                context.shorts[index - 1]["subtitles"] = str(ass_path)
            io.report(int(index / total * 100), f"Captioned {index}/{total}")
        context.short_captions = captions
        context.hashes["captions"] = digest_payload(captions)
        io.report(100, f"{len(captions)} caption files ready")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(Path(path) for path in context.short_captions.values())
