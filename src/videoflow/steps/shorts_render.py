"""Render selected Shorts to MP4 with optional burned captions."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.caption_presets import apply_preset
from videoflow.application.fonts import fonts_dir
from videoflow.application.sfx import sfx_dir
from videoflow.application.short_composition.io import (
    read_cues,
    read_manifest,
    read_plan,
)
from videoflow.application.short_composition.render import (
    SfxRenderCue,
    build_commands,
    build_segment_renders,
    execute_commands,
    nvenc_available,
    safe_output_name,
    write_render_report,
)
from videoflow.application.shorts import (
    build_ass,
    build_ass_lines,
    caption_lines,
    sentence_events,
    slugify,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.config import CaptionStyle
from videoflow.domain.errors import IngestError, StateNotReadyError
from videoflow.domain.scenes import ScenesManifest
from videoflow.domain.short_composition import ShortCompositionPlan
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


class ShortRenderParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_path: str = ""
    captions_path: str = ""
    cues_path: str = ""
    cam_video_path: str = ""
    screen_video_path: str = ""
    cam_side: Literal["right", "left"] = "right"
    output_name: str = "short.mp4"
    compute_policy: Literal["auto", "local", "local_gpu", "remote", "remote_only"] = "auto"
    allow_slow_cpu_fallback: bool = False
    encoder: Literal["auto", "nvenc", "libx264"] = "auto"
    burn_captions: bool = True
    smooth_track: bool = False
    keep_intermediates: bool = False
    strict: bool = True
    timeout_sec: float = Field(default=1800.0, ge=30.0, le=7200.0)


def _plan(context: PipelineContext, override: str) -> ShortCompositionPlan:
    return read_plan(context, override, step="short.render")


def _manifest(context: PipelineContext) -> ScenesManifest:
    return read_manifest(context, step="short.render")


def _captions(context: PipelineContext, override: str) -> Path | None:
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None
    raw = context.artifacts.get("short_captions", "")
    path = Path(raw) if raw else None
    return path if path is not None and path.is_file() else None


def _cues(context: PipelineContext, override: str) -> dict[str, Any]:
    return read_cues(context, override)


def _sfx_cues(cues: dict[str, Any], warnings: list[str]) -> list[SfxRenderCue]:
    result: list[SfxRenderCue] = []
    for item in cues.get("sfx") or []:
        if not isinstance(item, dict):
            continue
        asset = str(item.get("asset") or "").strip()
        if not asset:
            continue
        path = sfx_dir() / Path(asset).name
        if not path.is_file():
            warnings.append(f"SFX asset is missing and was skipped: {asset}")
            continue
        try:
            time_sec = float(item.get("time_sec") or 0.0)
            volume_db = float(item.get("volume_db") or -18.0)
        except (TypeError, ValueError):
            continue
        result.append(
            SfxRenderCue(path=path, time_sec=max(0.0, time_sec), volume_db=volume_db)
        )
    return result


def _drop_missing_broll(
    plan: ShortCompositionPlan,
    warnings: list[str],
) -> ShortCompositionPlan:
    segments = []
    for segment in plan.segments:
        if segment.layout != "SPLIT_BROLL":
            segments.append(segment)
            continue
        if segment.broll_source is None or not segment.broll_source.path:
            warnings.append(
                f"{segment.seg_id}: B-roll source is missing; using FULL_FACE"
            )
            segments.append(
                segment.model_copy(
                    update={
                        "layout": "FULL_FACE",
                        "broll_source": None,
                        "face_zoom": 1.12,
                    }
                )
            )
            continue
        path = Path(segment.broll_source.path).expanduser()
        if segment.broll_source.type == "stock" or path.is_file():
            segments.append(segment)
            continue
        warnings.append(
            f"{segment.seg_id}: B-roll disappeared before render; using FULL_FACE"
        )
        segments.append(
            segment.model_copy(
                update={
                    "layout": "FULL_FACE",
                    "broll_source": None,
                    "face_zoom": 1.12,
                }
            )
        )
    return plan.model_copy(update={"segments": segments})


def _has_audio_stream(path: Path) -> bool:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return True
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=index",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    return completed.returncode == 0 and bool(completed.stdout.strip())


def _ending(cues: dict[str, Any], plan: ShortCompositionPlan) -> tuple[float, float, int]:
    raw = cues.get("ending")
    ending = raw if isinstance(raw, dict) else {}
    try:
        content_end = float(ending.get("content_end_sec") or plan.duration_sec)
        effective_end = float(
            ending.get("effective_end_sec") or content_end + plan.end_padding_ms / 1000.0
        )
        fade_ms = int(ending.get("fade_out_ms") or 80)
    except (TypeError, ValueError):
        content_end, effective_end, fade_ms = plan.duration_sec, plan.duration_sec + 0.35, 80
    padding = max(0.0, effective_end - content_end)
    fade_start = max(0.0, effective_end - max(0, fade_ms) / 1000.0)
    return padding, fade_start, fade_ms


@register_step
class ShortRenderStep(BaseStep):
    type = "short.render"
    title = "Render dynamic Short"
    description = (
        "Build per-segment filter scripts, render micro-clips, concat, burn ASS, "
        "mix SFX, and encode with NVENC or libx264."
    )
    status = "available"
    icon = "▶"
    color = "#ef4444"
    requires = ("short.captions",)
    produces = ("short_render",)
    params_model = ShortRenderParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ShortRenderParams.model_validate(params)
        plan = _drop_missing_broll(_plan(context, options.plan_path), context.warnings)
        manifest = _manifest(context)
        if plan.source_topology == "dual_file" and not options.screen_video_path:
            raise IngestError(
                "dual_file Short render needs screen_video_path; pass it explicitly"
            )
        captions = _captions(context, options.captions_path)
        if options.burn_captions and captions is None:
            raise StateNotReadyError(
                "Caption ASS is missing; run short.captions or set burn_captions=false"
            )
        font_paths: list[str] = []
        if options.burn_captions and captions is not None:
            from videoflow.application.remote_fonts import remote_font_paths

            font_paths = remote_font_paths()
        cues = _cues(context, options.cues_path)
        sfx = _sfx_cues(cues, context.warnings)
        padding, fade_start, fade_ms = _ending(cues, plan)
        broll_paths = {
            str(segment.broll_source.path): Path(segment.broll_source.path).expanduser()
            for segment in plan.segments
            if segment.broll_source is not None and segment.broll_source.path
        }
        source = Path(
            options.cam_video_path
            or plan.source_video_path
            or context.source
        ).expanduser()
        screen = (
            Path(options.screen_video_path).expanduser()
            if options.screen_video_path
            else None
        )
        context.metadata["short_smooth_track"] = options.smooth_track
        warnings: list[str] = []
        renders = build_segment_renders(
            plan,
            manifest,
            smooth_track=options.smooth_track,
            cam_side=options.cam_side,
            broll_paths=broll_paths,
            screen_separate=screen is not None,
        )
        if not _has_audio_stream(source):
            warnings.append(
                "Source has no audio stream; using silent audio for captions/SFX"
            )
            renders = [replace(render, has_audio=False) for render in renders]
        output_name = safe_output_name(
            options.output_name, default="short.mp4", suffix=".mp4"
        )
        output = Path(context.output) / "shorts" / plan.short_id / output_name
        last_commands: list[Any] = []

        def make_commands(encoder: str, *, remote: bool = False):
            from videoflow.application.fonts import fonts_dir

            return build_commands(
                renders,
                source=source,
                screen=screen,
                captions=captions if options.burn_captions else None,
                sfx=sfx,
                output_name=output_name,
                fps=plan.target_fps,
                encoder=encoder,
                fade_start=fade_start,
                fade_ms=fade_ms,
                padding_sec=padding,
                fontsdir=None if remote else str(fonts_dir()),
            )

        def local_run(encoder: str) -> Path:
            local_encoder = (
                "nvenc"
                if encoder == "nvenc"
                or (encoder == "auto" and nvenc_available())
                else "libx264"
            )
            commands = make_commands(local_encoder)
            last_commands.append(commands)
            parent = Path(context.work) / "shorts" / plan.short_id
            parent.mkdir(parents=True, exist_ok=True)
            work = Path(
                tempfile.mkdtemp(prefix="short-render-", dir=str(parent))
            )
            try:
                rendered = execute_commands(
                    commands,
                    work,
                    check_cancel=io.check_cancel,
                    segment_cache=parent / "segment_cache",
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(rendered, output)
            finally:
                if not options.keep_intermediates:
                    shutil.rmtree(work, ignore_errors=True)
            context.metadata["short_render_encoder"] = local_encoder
            return output

        placement = "local"
        degraded = False
        reason = ""
        if options.compute_policy in {"local", "local_gpu"}:
            final = local_run(options.encoder)
        else:
            try:
                from videoflow.application.compute import (
                    guard_remote_policy,
                    router_from_settings,
                )

                router = router_from_settings()
                guard_remote_policy(
                    router,
                    "short_render",
                    compute_policy=options.compute_policy,
                    allow_slow_cpu_fallback=options.allow_slow_cpu_fallback,
                    error_cls=IngestError,
                )
                if options.compute_policy == "remote_only":
                    decision = router.decide("short_render")
                    if not decision.is_remote:
                        raise IngestError(
                            "Remote Short render requested but unavailable: "
                            f"{decision.reason}"
                        )
                    worker_nvenc = bool(getattr(router.health(), "nvenc", False))
                    encoder_name = (
                        "nvenc"
                        if options.encoder == "nvenc"
                        or (options.encoder == "auto" and worker_nvenc)
                        else "libx264"
                    )
                    commands = make_commands(encoder_name, remote=True)
                    last_commands.append(commands)
                    final = self._remote_render(
                        router, commands, output, options.timeout_sec, font_paths
                    )
                    placement = decision.execution_node
                    context.metadata["short_render_encoder"] = encoder_name
                else:
                    worker_health = router.health()
                    worker_nvenc = bool(getattr(worker_health, "nvenc", False))

                    def remote_run() -> Path:
                        encoder_name = (
                            "nvenc"
                            if options.encoder == "nvenc"
                            or (options.encoder == "auto" and worker_nvenc)
                            else "libx264"
                        )
                        commands = make_commands(encoder_name, remote=True)
                        last_commands.append(commands)
                        context.metadata["short_render_encoder"] = encoder_name
                        return self._remote_render(
                            router,
                            commands,
                            output,
                            options.timeout_sec,
                            font_paths,
                        )

                    outcome = router.execute(
                        "short_render",
                        remote_run,
                        lambda: local_run(options.encoder),
                        compute_policy=options.compute_policy,
                        allow_slow_cpu_fallback=options.allow_slow_cpu_fallback,
                    )
                    final = outcome["value"]
                    placement = str(outcome.get("execution_node") or "local")
                    degraded = bool(outcome.get("degraded"))
                    reason = str(outcome.get("degraded_reason") or "")
            except IngestError:
                raise
            except Exception as exc:  # noqa: BLE001 - local fallback is the contract
                if options.compute_policy == "remote_only":
                    raise IngestError(f"Remote Short render unavailable: {exc}") from exc
                warnings.append(f"Remote Short render failed; using local: {exc}")
                final = local_run(options.encoder)
                placement = "local"
                degraded = True
                reason = str(exc)
        probe = FFmpegAdapter().probe(final)
        if (probe.width, probe.height) != (1080, 1920):
            warnings.append(
                f"Rendered canvas is {probe.width}x{probe.height}, expected 1080x1920"
            )
        report_path = output.with_name("short_render.json")
        report = write_render_report(
            last_commands[-1],
            path=report_path,
            placement=placement,
            degraded=degraded,
            reason=reason,
            encoder=str(context.metadata.get("short_render_encoder") or "auto"),
            output=final,
        )
        report["warnings"] = warnings
        context.metadata["short_render"] = report
        context.artifacts["short_render"] = str(final)
        context.artifacts["short_render_report"] = str(report_path)
        context.hashes["short.render"] = digest_payload(report)
        for warning in warnings:
            if warning not in context.warnings:
                context.warnings.append(warning)
        io.report(100, f"Rendered {final.name}")

    def _remote_render(
        self,
        router: Any,
        commands: Any,
        output: Path,
        timeout_sec: float,
        font_paths: list[str] | None = None,
    ) -> Path:
        payload = commands.to_payload()
        if font_paths:
            payload["font_paths"] = list(font_paths)
        result = router.submit(
            "short_render",
            {
                "inputs": [str(path) for path in commands.inputs],
                "params": payload,
                "timeout_sec": timeout_sec,
            },
            timeout=timeout_sec,
        )
        path = Path(str(result.get("path") or ""))
        if not path.is_file():
            raise IngestError("Remote Short render returned no output file")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, output)
        return output


__all__ = ["ShortRenderParams", "ShortRenderStep"]
