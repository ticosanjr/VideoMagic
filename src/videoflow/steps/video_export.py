"""Direct video export with explicit speed presets."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.export_names import timestamped_basename, unique_path
from videoflow.application.master_export import MasterLook, render_master
from videoflow.application.render_gate import render_gate
from videoflow.application.render_inputs import read_filters
from videoflow.application.subtitles import resolve_subtitle_track
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ExportError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step

VideoPreset = Literal["ultrafast", "fast", "balanced", "quality"]

_PROFILES: dict[str, tuple[str, int]] = {
    "ultrafast": ("ultrafast", 30),
    "fast": ("veryfast", 26),
    "balanced": ("medium", 23),
    "quality": ("slow", 18),
}


class VideoExportParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: VideoPreset = "ultrafast"
    subdir: str = Field(default="exports", max_length=120)
    filename_mode: Literal["source_timestamp", "fixed"] = "source_timestamp"
    filename: str = Field(default="video.mp4", min_length=1, max_length=200)
    audio_source: Literal["timeline", "mix"] = "timeline"
    draft_scale: float = Field(default=0.0, ge=0.0, le=1.0)
    motion_blur: bool | None = None
    lut_path: str = ""
    grain_amount: float = Field(default=0.0, ge=0.0, le=1.0)
    grain_fps: float = Field(default=12.0, ge=1.0, le=60.0)


@register_step
class VideoExportStep(BaseStep):
    type = "export.video"
    title = "Export video"
    description = "Render the timeline to a direct video file. Ultrafast is the default."
    requires = ()
    produces = ("video",)
    params_model = VideoExportParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = VideoExportParams.model_validate(params)
        if context.state is None:
            raise ExportError("The video export requires a timeline")
        directory = context.output / options.subdir
        directory.mkdir(parents=True, exist_ok=True)
        if options.filename_mode == "source_timestamp":
            destination = unique_path(directory, f"{timestamped_basename(context.source)}.mp4")
        else:
            name = Path(options.filename).name
            if not name or name in {".", ".."}:
                raise ExportError("Video filename is invalid")
            destination = directory / name
        context.metadata["video_export_name"] = destination.name
        context.metadata["video_filename_mode"] = options.filename_mode
        preset, crf = _PROFILES[options.preset]
        io.report(10, f"Rendering video with the {options.preset} preset")
        adapter = (
            io.adapter
            if getattr(io.adapter, "render", None) is not None
            else FFmpegAdapter(cancel_event=io.cancel_event)
        )
        audio_filters = read_filters(context.output / "audio" / "master-filters.json")
        video_filters = list(read_filters(context.output / "color" / "filters.json"))
        if options.lut_path:
            lut = Path(options.lut_path).expanduser()
            if not lut.is_file():
                context.warnings.append(f"LUT not found: {lut}")
        ass_path = resolve_subtitle_track(context.output)
        if options.audio_source == "mix":
            mix = Path(context.artifacts.get("audio_mix") or context.output / "audio" / "final.wav")
            if not mix.is_file():
                raise ExportError("Video export requested the mix, but no mixed audio exists.")
        look = MasterLook(
            lut_path=options.lut_path,
            grain_amount=options.grain_amount,
            grain_fps=options.grain_fps,
            video_filters=tuple(video_filters),
            audio_filters=tuple(audio_filters),
        )

        def progress(value: int) -> None:
            io.check_cancel()
            io.report(10 + int(max(0, min(100, value)) * 0.85), "Rendering video")

        scale_height = None
        if options.draft_scale and 0 < options.draft_scale < 1 and context.media is not None:
            scale_height = max(144, int(context.media.height * options.draft_scale))
        with render_gate.hold("export.video", str(context.output)):
            render_master(
                context.state,
                destination,
                output=context.output,
                adapter=adapter,
                audio_source=options.audio_source,
                ass_path=ass_path,
                look=look,
                crf=crf,
                preset=preset,
                progress=progress,
                scale_height=scale_height,
                cache_dir=context.output / "render" / "segments",
            )
        context.artifacts["video"] = str(destination)
        context.hashes["export.video"] = digest_payload(
            {
                "path": str(destination),
                "preset": options.preset,
                "crf": crf,
                "audio_source": options.audio_source,
            }
        )
        io.report(100, f"Video ready: {destination.name}")

    def is_cacheable(self, params: BaseModel) -> bool:
        return getattr(params, "filename_mode", "source_timestamp") != "source_timestamp"

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("video")
        return (Path(path),) if path else ()
