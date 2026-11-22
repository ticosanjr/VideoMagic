"""Direct video export with explicit speed presets."""

from __future__ import annotations

import shutil
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
    fps: int | Literal["source"] = 30
    subdir: str = Field(default="exports", max_length=120)
    filename_mode: Literal["source_timestamp", "fixed"] = "source_timestamp"
    filename: str = Field(default="video.mp4", min_length=1, max_length=200)
    audio_source: Literal["timeline", "mix"] = "timeline"
    compute_policy: Literal["auto", "local", "remote", "remote_only"] = "auto"
    allow_slow_cpu_fallback: bool = False
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

        scale_height = None
        if options.draft_scale and 0 < options.draft_scale < 1 and context.media is not None:
            scale_height = max(144, int(context.media.height * options.draft_scale))
        def render_local(
            target: Path,
            *,
            local_preset: str,
            local_crf: int,
            start: int = 10,
            span: int = 85,
        ) -> None:
            def local_progress(value: int) -> None:
                io.check_cancel()
                io.report(start + int(max(0, min(100, value)) * span / 100), "Rendering video")

            try:
                render_master(
                    context.state,
                    target,
                    output=context.output,
                    adapter=adapter,
                    audio_source=options.audio_source,
                    ass_path=ass_path,
                    look=look,
                    crf=local_crf,
                    preset=local_preset,
                    fps=None if options.fps == "source" else int(options.fps),
                    progress=local_progress,
                    scale_height=scale_height,
                    cache_dir=context.output / "render" / "segments",
                )
            except Exception as exc:  # noqa: BLE001 - preserve evidence
                from videoflow.application.export_evidence import (
                    preserve_failed_export,
                )

                preserve_failed_export(
                    context.output,
                    error=str(exc),
                    command="render_master",
                    paths=(target,),
                )
                raise

        placement = "local"
        encoder = "libx264"
        remote_error = ""
        if options.compute_policy != "local":
            try:
                from videoflow.application.compute import (
                    guard_remote_policy,
                    router_from_settings,
                )

                router = router_from_settings()
                guard_remote_policy(
                    router,
                    "render_nvenc",
                    compute_policy=options.compute_policy,
                    allow_slow_cpu_fallback=options.allow_slow_cpu_fallback,
                    error_cls=ExportError,
                )
                health = router.health()
                if not bool(getattr(health, "nvenc", False)):
                    raise ExportError(
                        "gpu_required_for_operation: worker reports NVENC unavailable: "
                        + (getattr(health, "nvenc_error", "") or "h264_nvenc failed")
                    )
                mezzanine = context.work / "export_mezzanine.mp4"
                io.report(10, "Rendering mezzanine for the Windows NVENC encode")
                render_local(mezzanine, local_preset="ultrafast", local_crf=18, start=10, span=45)
                params: dict[str, object] = {
                    "output_name": destination.name,
                    "preset": "p4",
                    "tune": "hq",
                    "cq": 19,
                    "audio_bitrate": "192k",
                }
                if context.media is not None:
                    params["width"] = context.media.width
                    params["height"] = context.media.height
                if options.fps != "source":
                    params["fps"] = int(options.fps)
                if ass_path is not None:
                    from videoflow.application.remote_fonts import remote_font_paths

                    params["ass_path"] = str(ass_path)
                    fonts = remote_font_paths()
                    if fonts:
                        params["font_paths"] = fonts
                io.report(58, "Uploading mezzanine to the GPU worker")
                result = router.submit(
                    "render_nvenc",
                    {
                        "inputs": [str(mezzanine)],
                        "params": params,
                        "timeout_sec": 3600.0,
                    },
                    timeout=3600.0,
                )
                remote_path = Path(str(result.get("path") or ""))
                if not remote_path.is_file():
                    raise ExportError("Remote NVENC render returned no file")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(remote_path, destination)
                placement = str(result.get("execution_node") or "remote_gpu")
                encoder = "nvenc"
            except ExportError as exc:
                if (
                    options.compute_policy in {"remote", "remote_only"}
                    and not options.allow_slow_cpu_fallback
                ):
                    raise
                remote_error = str(exc)
                context.warnings.append(f"Remote NVENC export unavailable: {exc}")
                placement = "local"
                encoder = "libx264"
        if placement == "local":
            with render_gate.hold("export.video", str(context.output)):
                render_local(destination, local_preset=preset, local_crf=crf)
        context.metadata["video_export_placement"] = placement
        context.metadata["video_export_encoder"] = encoder
        if remote_error:
            context.metadata["video_export_degraded_reason"] = remote_error
        context.artifacts["video"] = str(destination)
        context.hashes["export.video"] = digest_payload(
            {
                "path": str(destination),
                "preset": options.preset,
                "crf": crf,
                "fps": options.fps,
                "audio_source": options.audio_source,
            }
        )
        io.report(100, f"Video ready: {destination.name}")

    def is_cacheable(self, params: BaseModel) -> bool:
        return getattr(params, "filename_mode", "source_timestamp") != "source_timestamp"

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("video")
        return (Path(path),) if path else ()
