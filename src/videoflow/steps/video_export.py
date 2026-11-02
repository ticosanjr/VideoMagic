"""Direct video export with explicit speed presets."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.render_inputs import read_filters
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ExportError
from videoflow.exporters.mp4 import export_mp4
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
    filename: str = Field(default="video.mp4", min_length=1, max_length=200)


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
        name = Path(options.filename).name
        if not name or name in {".", ".."}:
            raise ExportError("Video filename is invalid")
        destination = context.output / options.subdir / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        preset, crf = _PROFILES[options.preset]
        io.report(10, f"Rendering video with the {options.preset} preset")
        adapter = (
            io.adapter
            if getattr(io.adapter, "render", None) is not None
            else FFmpegAdapter(cancel_event=io.cancel_event)
        )
        audio_filters = read_filters(context.output / "audio" / "master-filters.json")
        video_filters = read_filters(context.output / "color" / "filters.json")
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
        context.artifacts["video"] = str(destination)
        context.hashes["export.video"] = digest_payload(
            {
                "path": str(destination),
                "preset": options.preset,
                "crf": crf,
            }
        )
        io.report(100, f"Video ready: {destination.name}")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("video")
        return (Path(path),) if path else ()
