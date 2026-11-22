"""Render selected Shorts to MP4 with optional burned captions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.caption_presets import apply_preset
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
from videoflow.domains.media.broll_approval import load_approvals
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
    second_source_path: str | None = None
    mix_second_audio: bool = False
    broll_enabled: bool = True
    preset: str = ""
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
    layout: Literal[
        "auto",
        "none",
        "cutout",
        "rounded_window",
        "full_screen",
        "split_top_visual",
        "headline_card",
        "fullscreen_punchin",
        "pip_bottom_right",
    ] = "auto"
    cutout_corner_radius: float = Field(default=0.08, ge=0.0, le=0.5)
    cutout_margin: float = Field(default=0.04, ge=0.0, le=0.3)
    cutout_head_overlap: float = Field(default=0.12, ge=0.0, le=0.4)
    draft_scale: float = Field(default=1.0, ge=0.1, le=1.0)


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
        if options.preset:
            options = options.model_copy(
                update={"caption_style": apply_preset(options.preset, options.caption_style)}
            )
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
        manifest_path = shorts_dir / "render-manifest.json"
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = payload.get("shorts", {}) if isinstance(payload, dict) else {}
        except (OSError, ValueError):
            manifest = {}
        if not isinstance(manifest, dict):
            manifest = {}
        reused = 0
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
                    effect=options.caption_style.effect,
                    max_words=2,
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
                            layout=str(entry.get("layout") or ""),
                        ),
                    )
                else:
                    events = sentence_events(kept, clip.pieces, sample_rate=media.audio_sample_rate)
                    if events:
                        ass_path = shorts_dir / f"{slug}.ass"
                        write_text(
                            ass_path,
                            build_ass(
                                events,
                                style=options.caption_style,
                                width=width,
                                height=height,
                                layout=str(entry.get("layout") or ""),
                            ),
                        )
            broll_clips: list[tuple[Path, float, float]] = []
            sfx_clips: list[tuple[Path, float, float]] = []
            sfx_plan = context.metadata.get("sfx_plan")
            if isinstance(sfx_plan, dict):
                for cue in sfx_plan.get(clip.title, []):
                    if not isinstance(cue, dict) or not cue.get("path"):
                        continue
                    path = Path(str(cue["path"])).expanduser()
                    if path.is_file():
                        sfx_clips.append((path, float(cue.get("start_sec") or 0.0), 0.9))
            plan = context.metadata.get("broll_plan")
            if options.broll_enabled and isinstance(plan, dict):
                broll_entries = plan.get(clip.title)
                approvals = load_approvals(context.output)
                approval = approvals.get(clip.title)
                if isinstance(broll_entries, list) and approval is not None:
                    order = approval.get("order") or approval.get("approved") or []
                    broll_entries = [
                        broll_entries[index] for index in order if 0 <= index < len(broll_entries)
                    ]
                if isinstance(broll_entries, list):
                    for item in broll_entries:
                        if not isinstance(item, dict) or not item.get("path"):
                            continue
                        path = Path(str(item["path"])).expanduser()
                        if not path.is_file():
                            context.warnings.append(f"B-roll asset missing: {path}")
                            continue
                        broll_clips.append(
                            (
                                path,
                                float(item.get("start_sec") or 0.0),
                                float(item.get("duration_sec") or 2.0),
                            )
                        )
            layout_style = self._layout_for(options.layout, context, index - 1, clip.title)
            cutout = layout_style in {"cutout", "rounded_window", "headline_card"}
            render_width = max(16, int(width * options.draft_scale))
            render_height = max(16, int(height * options.draft_scale))
            destination = shorts_dir / f"{slug}.mp4"
            music_path = Path(options.music_path) if options.music_path else None
            second_source_path = (
                Path(options.second_source_path) if options.second_source_path else None
            )
            key = digest_payload(
                {
                    "pieces": [list(piece) for piece in clip.pieces],
                    "width": width,
                    "height": height,
                    "ass": (
                        Path(ass_path).stat().st_mtime_ns
                        if ass_path is not None and Path(ass_path).is_file()
                        else 0
                    ),
                    "style": options.caption_style.model_dump(mode="json"),
                    "burn_subtitles": options.burn_subtitles,
                    "overlay": options.overlay_path,
                    "overlay_position": options.overlay_position,
                    "overlay_width_ratio": options.overlay_width_ratio,
                    "filters": list(options.audio_filters),
                    "broll": [
                        [str(path), start, duration] for path, start, duration in broll_clips
                    ],
                    "sfx": [[str(path), start, volume] for path, start, volume in sfx_clips],
                    "music": [
                        str(music_path) if music_path else "",
                        options.music_volume,
                        options.music_ducking,
                    ],
                    "cards": [options.intro_path, options.outro_path],
                    "split": [options.split_screen, options.split_screen_zoom],
                    "second": str(second_source_path) if second_source_path else "",
                    "crop": [
                        clip.crop_focus_x,
                        clip.crop_focus_y,
                        list(clip.crop_keyframes),
                    ],
                    "layout": layout_style,
                    "draft_scale": options.draft_scale,
                    "cutout": [
                        options.cutout_corner_radius,
                        options.cutout_margin,
                        options.cutout_head_overlap,
                    ],
                }
            )
            cached = manifest.get(slug)
            skip = bool(
                isinstance(cached, dict) and cached.get("key") == key and destination.is_file()
            )
            if skip:
                reused += 1
            else:
                layout_args: dict[str, object] = {}
                if layout_style in {
                    "split_top_visual",
                    "headline_card",
                    "fullscreen_punchin",
                    "pip_bottom_right",
                }:
                    layout_args = {
                        "layout_mode": layout_style,
                        "punch_in_scale": float(entry.get("punch_in_scale") or 1.06),
                        "visual_path": (
                            Path(str(entry["visual_path"]))
                            if entry.get("visual_path")
                            else None
                        ),
                        "headline_text": (
                            str(entry.get("headline_text") or entry.get("title") or "")
                            if layout_style == "headline_card"
                            else ""
                        ),
                    }
                adapter.render_short(
                    Path(context.source),
                    clip.pieces,
                    destination,
                    sample_rate=media.audio_sample_rate,
                    ass_path=ass_path,
                    width=render_width,
                    height=render_height,
                    fontsdir=str(fonts_dir()),
                    audio_filters=tuple(options.audio_filters),
                    overlay_path=(
                        Path(str(entry.get("overlay_path") or options.overlay_path))
                        if entry.get("overlay_path") or options.overlay_path
                        else None
                    ),
                    overlay_position=options.overlay_position,
                    overlay_margin=options.overlay_margin,
                    overlay_width_ratio=options.overlay_width_ratio,
                    overlay_opacity=options.overlay_opacity,
                    crop_focus_x=clip.crop_focus_x,
                    crop_focus_y=clip.crop_focus_y,
                    **(
                        {"crop_keyframes": tuple(clip.crop_keyframes)}
                        if len({focus for _time, focus in clip.crop_keyframes}) > 1
                        else {}
                    ),
                    split_screen=options.split_screen or bool(entry.get("split_screen")),
                    split_screen_zoom=float(
                        entry.get("split_screen_zoom", options.split_screen_zoom)
                    ),
                    split_screen_focus_left=float(
                        entry.get("split_screen_focus_left", options.split_screen_focus_left)
                    ),
                    split_screen_focus_right=float(
                        entry.get("split_screen_focus_right", options.split_screen_focus_right)
                    ),
                    second_source_path=(
                        Path(options.second_source_path) if options.second_source_path else None
                    ),
                    mix_second_audio=options.mix_second_audio,
                    broll_clips=broll_clips or None,
                    sfx_clips=sfx_clips or None,
                    music_path=Path(options.music_path) if options.music_path else None,
                    music_volume=options.music_volume,
                    music_ducking=options.music_ducking,
                    music_fade_in_ms=options.music_fade_in_ms,
                    music_fade_out_ms=options.music_fade_out_ms,
                    intro_path=Path(options.intro_path) if options.intro_path else None,
                    outro_path=Path(options.outro_path) if options.outro_path else None,
                    intro_duration_sec=options.intro_duration_sec,
                    outro_duration_sec=options.outro_duration_sec,
                    **layout_args,
                    **(
                        {
                            "cutout": True,
                            "cutout_corner_radius": options.cutout_corner_radius,
                            "cutout_margin": options.cutout_margin,
                            "cutout_head_overlap": options.cutout_head_overlap,
                        }
                        if cutout
                        else {}
                    ),
                )
            manifest[slug] = {
                "key": key,
                "path": str(destination),
                "reused": skip,
            }
            entry["path"] = str(destination)
            if ass_path is not None:
                entry["subtitles"] = str(ass_path)
            else:
                entry.pop("subtitles", None)
            entry["aspect_ratio"] = entry.get("aspect_ratio", "9:16")
            entry["layout"] = layout_style
            rendered.append(entry)

        write_text(
            manifest_path,
            json.dumps({"shorts": manifest}, indent=2) + "\n",
        )
        context.shorts = rendered
        if rendered:
            write_text(
                context.output / "shorts.json",
                json.dumps({"ok": True, "clips": rendered}, indent=2) + "\n",
            )
        context.hashes["shorts_render"] = digest_payload([entry.get("path") for entry in rendered])
        message = f"{len(rendered)} shorts rendered ({reused} reused)"
        io.emit("info", message, module="shorts")
        io.report(100, message)

    @staticmethod
    def _layout_for(requested: str, context: PipelineContext, index: int, title: str) -> str:
        if requested != "auto":
            return requested
        plan = context.metadata.get("layout_plan")
        if not isinstance(plan, dict):
            return "none"
        for item in plan.get("clips", []):
            if not isinstance(item, dict):
                continue
            if item.get("index") == index or item.get("title") == title:
                layout = str(item.get("layout") or "none")
                allowed = {
                    "cutout",
                    "rounded_window",
                    "full_screen",
                    "split_top_visual",
                    "headline_card",
                    "fullscreen_punchin",
                    "pip_bottom_right",
                }
                return layout if layout in allowed else "none"
        return "none"

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        outputs = [Path(str(entry["path"])) for entry in context.shorts if entry.get("path")]
        report = context.output / "shorts.json"
        return (*outputs, report) if outputs else ()
