"""Render selected Shorts to MP4 with optional burned captions."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.fonts import fonts_dir
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
from videoflow.steps.common import adapter_for, digest_payload, require_media
from videoflow.steps.registry import register_step


class RenderShortsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    burn_subtitles: bool = True
    split_screen: bool = False
    split_screen_zoom: float = Field(default=1.0, ge=1.0, le=2.0)
    split_screen_focus_left: float = Field(default=0.5, ge=0.0, le=1.0)
    split_screen_focus_right: float = Field(default=0.5, ge=0.0, le=1.0)
    broll_enabled: bool = True
    caption_style: CaptionStyle = Field(default_factory=CaptionStyle)
    audio_filters: list[str] = Field(default_factory=list)
    overlay_path: str | None = None
    overlay_position: str = "bottom_right"
    overlay_margin: int = 32
    overlay_width_ratio: float = 0.18
    overlay_opacity: float = 0.9
    music_path: str | None = None
    music_volume: float = 0.18
    music_ducking: bool = True
    music_fade_in_ms: int = 250
    music_fade_out_ms: int = 500
    intro_path: str | None = None
    outro_path: str | None = None
    intro_duration_sec: float = 2.0
    outro_duration_sec: float = 2.0


@register_step
class RenderShortsStep(BaseStep):
    type = "shorts.render"
    title = "Render Shorts"
    description = "Burn captions and render each selected piece list to a vertical MP4."
    requires = ("shorts.select",)
    produces = ("short_files",)
    params_model = RenderShortsParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = RenderShortsParams.model_validate(params)
        media = require_media(context)
        if not context.selected_shorts:
            io.report(100, "No Shorts selected")
            return
        adapter = adapter_for(context, io)
        shorts_dir = context.output / "shorts"
        shorts_dir.mkdir(parents=True, exist_ok=True)
        discard = set(context.discard_sentence_ids)
        kept = [item for item in context.transcript if item.id not in discard]
        short_entries = {entry.get("title"): dict(entry) for entry in context.shorts}
        rendered: list[dict[str, object]] = []
        total = max(1, len(context.selected_shorts))
        for index, clip in enumerate(context.selected_shorts, start=1):
            io.check_cancel()
            io.report(int(index / total * 90), f"Rendering {index}/{total}")
            entry = short_entries.get(clip.title, clip.to_dict(media.audio_sample_rate))
            slug = slugify(clip.title, index)
            width = int(entry.get("width", 1080))
            height = int(entry.get("height", 1920))
            ass_path: Path | None = None
            cached_caption = context.short_captions.get(clip.title)
            captions_disabled = bool(context.metadata.get("captions_disabled"))
            if options.burn_subtitles and cached_caption and Path(cached_caption).is_file():
                ass_path = Path(cached_caption)
            elif options.burn_subtitles and not captions_disabled:
                lines = caption_lines(
                    kept,
                    clip.pieces,
                    sample_rate=media.audio_sample_rate,
                    word_timing=options.caption_style.word_timing,
                    warnings=context.warnings,
                )
                if lines:
                    ass_path = shorts_dir / f"{slug}.ass"
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
                    if events:
                        ass_path = shorts_dir / f"{slug}.ass"
                        write_text(
                            ass_path,
                            build_ass(
                                events,
                                style=options.caption_style,
                                width=width,
                                height=height,
                            ),
                        )
            broll = None
            plan = context.metadata.get("broll_plan")
            if options.broll_enabled and isinstance(plan, dict):
                broll_entries = plan.get(clip.title)
                if (
                    isinstance(broll_entries, list)
                    and broll_entries
                    and isinstance(broll_entries[0], dict)
                ):
                    broll = broll_entries[0]
            destination = shorts_dir / f"{slug}.mp4"
            adapter.render_short(
                Path(context.source),
                clip.pieces,
                destination,
                sample_rate=media.audio_sample_rate,
                ass_path=ass_path,
                width=width,
                height=height,
                fontsdir=str(fonts_dir()),
                audio_filters=tuple(options.audio_filters),
                overlay_path=Path(options.overlay_path) if options.overlay_path else None,
                overlay_position=options.overlay_position,
                overlay_margin=options.overlay_margin,
                overlay_width_ratio=options.overlay_width_ratio,
                overlay_opacity=options.overlay_opacity,
                crop_focus_x=clip.crop_focus_x,
                crop_focus_y=clip.crop_focus_y,
                split_screen=options.split_screen or bool(entry.get("split_screen")),
                split_screen_zoom=float(entry.get("split_screen_zoom", options.split_screen_zoom)),
                split_screen_focus_left=float(
                    entry.get("split_screen_focus_left", options.split_screen_focus_left)
                ),
                split_screen_focus_right=float(
                    entry.get("split_screen_focus_right", options.split_screen_focus_right)
                ),
                broll_path=Path(str(broll["path"])) if broll else None,
                broll_start_sec=float(broll.get("start_sec", 0.0)) if broll else 0.0,
                broll_duration_sec=float(broll.get("duration_sec", 2.0)) if broll else 2.0,
                music_path=Path(options.music_path) if options.music_path else None,
                music_volume=options.music_volume,
                music_ducking=options.music_ducking,
                music_fade_in_ms=options.music_fade_in_ms,
                music_fade_out_ms=options.music_fade_out_ms,
                intro_path=Path(options.intro_path) if options.intro_path else None,
                outro_path=Path(options.outro_path) if options.outro_path else None,
                intro_duration_sec=options.intro_duration_sec,
                outro_duration_sec=options.outro_duration_sec,
            )
            entry["path"] = str(destination)
            if ass_path is not None:
                entry["subtitles"] = str(ass_path)
            entry["aspect_ratio"] = entry.get("aspect_ratio", "9:16")
            rendered.append(entry)

        context.shorts = rendered
        if rendered:
            write_text(
                context.output / "shorts.json",
                json.dumps({"ok": True, "clips": rendered}, indent=2) + "\n",
            )
        context.hashes["shorts_render"] = digest_payload(
            [entry.get("path") for entry in rendered]
        )
        message = f"{len(rendered)} shorts rendered"
        io.emit("info", message, module="shorts")
        io.report(100, message)

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        outputs = [Path(str(entry["path"])) for entry in context.shorts if entry.get("path")]
        report = context.output / "shorts.json"
        return (*outputs, report) if outputs else ()
