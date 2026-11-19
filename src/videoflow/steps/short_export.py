"""Export a dynamic Short as FCPXML with V1/V2/A1/A2 tracks."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.scene_intel.io import read_json
from videoflow.application.sfx import sfx_dir
from videoflow.application.short_composition.render import (
    build_segment_renders,
    safe_output_name,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ExportError, StateNotReadyError
from videoflow.domain.scenes import ScenesManifest
from videoflow.domain.short_composition import ShortCompositionPlan
from videoflow.exporters.short_fcpxml import (
    CaptionClip,
    SfxClip,
    export_short_fcpxml,
    generate_face_clips,
    validate_short_fcpxml,
    write_short_export_report,
)
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class ShortExportParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_path: str = ""
    video_path: str = ""
    source_path: str = ""
    screen_path: str = ""
    cues_path: str = ""
    output_name: str = "short.fcpxml"
    generate_face_track: bool = True
    include_captions: bool = True
    force: bool = False
    check_media: bool = True
    strict: bool = True


def _audio_duration(path: Path) -> float:
    if path.suffix.casefold() == ".wav":
        try:
            with wave.open(str(path), "rb") as handle:
                rate = handle.getframerate()
                return handle.getnframes() / max(1, rate)
        except (OSError, wave.Error):
            pass
    return 1.0


def _plan(context: PipelineContext, override: str) -> ShortCompositionPlan:
    raw: dict[str, Any] = {}
    if override:
        raw = read_json(Path(override).expanduser())
    if not raw:
        raw = context.metadata.get("short_plan") or {}
    if not raw:
        artifact = context.artifacts.get("short_plan", "")
        raw = read_json(Path(artifact)) if artifact else {}
    if not raw:
        raise StateNotReadyError("Run short.plan before short.export")
    try:
        return ShortCompositionPlan.model_validate(raw)
    except ValueError as exc:
        raise ExportError(f"Invalid Short plan: {exc}") from exc


def _manifest(context: PipelineContext) -> ScenesManifest:
    raw = context.metadata.get("scenes_manifest")
    if not isinstance(raw, dict) or not raw:
        artifact = context.artifacts.get("scenes_manifest", "")
        raw = read_json(Path(artifact)) if artifact else {}
    if not raw:
        raise StateNotReadyError("Run scene.analyze before short.export")
    return ScenesManifest.model_validate(raw)


def _cues(context: PipelineContext, override: str) -> dict[str, Any]:
    if override:
        return read_json(Path(override).expanduser())
    raw = context.metadata.get("short_cues")
    if isinstance(raw, dict):
        return raw
    artifact = context.artifacts.get("short_cues", "")
    return read_json(Path(artifact)) if artifact else {}


@register_step
class ShortExportStep(BaseStep):
    type = "short.export"
    title = "Export Short FCPXML"
    description = (
        "Write V1 base, V2 face, A1 voice, and A2 SFX tracks plus editable "
        "captions and layout markers for Resolve."
    )
    status = "available"
    icon = "FCP"
    color = "#0ea5e9"
    requires = ("short.render",)
    produces = ("short_fcpxml",)
    params_model = ShortExportParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ShortExportParams.model_validate(params)
        plan = _plan(context, options.plan_path)
        manifest = _manifest(context)
        cues = _cues(context, options.cues_path)
        final_video = (
            Path(options.video_path).expanduser()
            if options.video_path
            else Path(context.artifacts.get("short_render", ""))
        )
        if not final_video.is_file():
            raise StateNotReadyError(
                "Rendered Short is missing; run short.render before short.export"
            )
        source = Path(
            options.source_path or plan.source_video_path or context.source
        ).expanduser()
        if not source.is_file():
            raise ExportError(f"Source media is offline: {source}")
        screen = Path(options.screen_path).expanduser() if options.screen_path else None
        warnings: list[str] = []
        broll_paths = {
            str(segment.broll_source.path): Path(segment.broll_source.path).expanduser()
            for segment in plan.segments
            if segment.broll_source is not None and segment.broll_source.path
        }
        renders = build_segment_renders(
            plan,
            manifest,
            smooth_track=bool(context.metadata.get("short_smooth_track")),
            broll_paths=broll_paths,
            screen_separate=screen is not None,
        )
        workspace = Path(context.output) / "shorts" / plan.short_id
        face_clips = []
        if options.generate_face_track:
            face_clips, face_warnings = generate_face_clips(
                renders,
                source,
                workspace / "fcpxml" / "face",
                fps=plan.target_fps,
                force=options.force,
                check_cancel=io.check_cancel,
                offset_base=plan.start,
            )
            warnings.extend(face_warnings)
            if not face_clips and options.strict:
                raise ExportError(
                    "V2 face track could not be generated; check the source and "
                    "face crop"
                )
        sfx: list[SfxClip] = []
        for item in cues.get("sfx") or []:
            if not isinstance(item, dict):
                continue
            asset = str(item.get("asset") or "").strip()
            path = sfx_dir() / Path(asset).name
            if not path.is_file():
                warnings.append(f"SFX asset missing: {asset}")
                continue
            sfx.append(
                SfxClip(
                    path=path,
                    offset_sec=max(0.0, float(item.get("time_sec") or 0.0)),
                    duration_sec=_audio_duration(path),
                )
            )
        captions: list[CaptionClip] = []
        if options.include_captions:
            for block in cues.get("captions") or []:
                if not isinstance(block, dict):
                    continue
                text = str(block.get("text") or "").strip()
                if not text:
                    continue
                captions.append(
                    CaptionClip(
                        start_sec=float(block.get("start") or 0.0),
                        end_sec=float(block.get("end") or 0.0),
                        text=text,
                        subtitle_y=int(block.get("subtitle_y") or 1360),
                    )
                )
        ending = cues.get("ending") if isinstance(cues.get("ending"), dict) else {}
        duration = float(
            ending.get("effective_end_sec")
            or plan.duration_sec + plan.end_padding_ms / 1000.0
        )
        source_duration = duration
        if context.media is not None:
            source_duration = (
                context.media.duration_frames
                * context.media.fps_den
                / max(1, context.media.fps_num)
            )
        else:
            try:
                media = FFmpegAdapter().probe(source)
                source_duration = (
                    media.duration_frames * media.fps_den / max(1, media.fps_num)
                )
            except Exception:  # noqa: BLE001 - metadata is advisory here
                pass
        output_name = safe_output_name(
            options.output_name, default="short.fcpxml", suffix=".fcpxml"
        )
        output = workspace / output_name
        xml_path = export_short_fcpxml(
            plan,
            output,
            final_video=final_video,
            source=source,
            face_clips=face_clips,
            sfx=sfx,
            captions=captions,
            source_duration=source_duration,
            duration_sec=duration,
            fps=plan.target_fps,
        )
        required_tracks = ["0", "-1"]
        if face_clips:
            required_tracks.append("1")
        if sfx:
            required_tracks.append("-2")
        validation = validate_short_fcpxml(
            xml_path,
            check_media=options.check_media,
            require_tracks=tuple(required_tracks),
        )
        report = {
            "ok": bool(validation["ok"]),
            "xml_path": str(xml_path),
            "final_video": str(final_video),
            "source": str(source),
            "duration_sec": round(duration, 3),
            "tracks": {
                "V1": 1,
                "V2": len(face_clips),
                "A1": len(plan.segments),
                "A2": len(sfx),
                "captions": len(captions),
            },
            "face_clips": [str(clip.path) for clip in face_clips],
            "sfx": [str(clip.path) for clip in sfx],
            "validation": validation,
            "warnings": warnings,
        }
        report_path = workspace / "short_export.json"
        write_short_export_report(report_path, report)
        context.metadata["short_export"] = report
        context.artifacts["short_fcpxml"] = str(xml_path)
        context.artifacts["short_export_report"] = str(report_path)
        context.hashes["short.export"] = digest_payload(report)
        for warning in warnings:
            if warning not in context.warnings:
                context.warnings.append(warning)
        if (validation["errors"] or warnings) and options.strict and validation["errors"]:
            raise ExportError("; ".join(str(item) for item in validation["errors"]))
        io.report(100, f"FCPXML exported with {len(face_clips)} face clip(s)")


__all__ = ["ShortExportParams", "ShortExportStep"]
