"""Direct video export with explicit speed presets."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.export_names import timestamped_basename, unique_path
from videoflow.application.render_inputs import read_filters
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ExportError
from videoflow.exporters.mp4 import export_mp4
from videoflow.runtime import find_binary
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
            destination = unique_path(
                directory, f"{timestamped_basename(context.source)}.mp4"
            )
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
        video_filters = read_filters(context.output / "color" / "filters.json")
        ass_path = context.output / "subtitles.ass"
        if not ass_path.is_file():
            ass_path = context.output / "titles.ass"

        def progress(value: int) -> None:
            io.check_cancel()
            io.report(10 + int(max(0, min(100, value)) * 0.85), "Rendering video")

        export_mp4(
            context.state,
            destination,
            adapter=adapter,
            crf=crf,
            preset=preset,
            audio_filters=audio_filters,
            video_filters=video_filters,
            ass_path=ass_path if ass_path.is_file() else None,
            progress=progress,
            cache_dir=context.output / "render" / "segments",
        )
        if options.audio_source == "mix":
            mix = context.artifacts.get("audio_mix") or context.output / "audio" / "final.wav"
            mix_path = Path(mix)
            if not mix_path.is_file():
                raise ExportError("Video export requested the mix, but no mixed audio exists.")
            _replace_audio(destination, mix_path)
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


def _replace_audio(video: Path, audio: Path) -> None:
    """Swap the rendered timeline audio for the approved final mix."""

    binary = find_binary("ffmpeg")
    if binary is None:
        raise ExportError("FFmpeg is required to mux the final audio mix.")
    temporary = video.with_name(f".{video.stem}.{uuid4().hex}.mix.mp4")
    command = [
        binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(temporary),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        temporary.unlink(missing_ok=True)
        raise ExportError(
            "Could not replace the video audio: "
            + (completed.stderr.strip() or f"exit {completed.returncode}")
        )
    temporary.replace(video)
