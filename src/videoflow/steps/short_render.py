"""Render a dynamic Short with local or remote NVENC execution."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.scene_intel.io import read_json
from videoflow.application.sfx import sfx_dir
from videoflow.application.short_composition.render import (
    SfxRenderCue,
    build_commands,
    build_segment_renders,
    execute_commands,
    nvenc_available,
    safe_output_name,
    write_render_report,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError, ShortPlanError, StateNotReadyError
from videoflow.domain.scenes import ScenesManifest
from videoflow.domain.short_composition import ShortCompositionPlan
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class ShortRenderParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_path: str = ""
    captions_path: str = ""
    cues_path: str = ""
    cam_video_path: str = ""
    screen_video_path: str = ""
    cam_side: Literal["right", "left"] = "right"
    output_name: str = "short.mp4"
    compute_policy: Literal["auto", "local", "remote", "remote_only"] = "auto"
    encoder: Literal["auto", "nvenc", "libx264"] = "auto"
    burn_captions: bool = True
    smooth_track: bool = False
    keep_intermediates: bool = False
    strict: bool = True
    timeout_sec: float = Field(default=1800.0, ge=30.0, le=7200.0)


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
        raise StateNotReadyError("Run short.plan before short.render")
    try:
        return ShortCompositionPlan.model_validate(raw)
    except ValueError as exc:
        raise ShortPlanError(f"Invalid Short plan: {exc}") from exc


def _manifest(context: PipelineContext) -> ScenesManifest:
    raw = context.metadata.get("scenes_manifest")
    if not isinstance(raw, dict) or not raw:
        artifact = context.artifacts.get("scenes_manifest", "")
        raw = read_json(Path(artifact)) if artifact else {}
    if not raw:
        raise StateNotReadyError("Run scene.analyze before short.render")
    try:
        return ScenesManifest.model_validate(raw)
    except ValueError as exc:
        raise ShortPlanError(f"Invalid scene manifest: {exc}") from exc


def _captions(context: PipelineContext, override: str) -> Path | None:
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None
    raw = context.artifacts.get("short_captions", "")
    path = Path(raw) if raw else None
    return path if path is not None and path.is_file() else None


def _cues(context: PipelineContext, override: str) -> dict[str, Any]:
    if override:
        return read_json(Path(override).expanduser())
    raw = context.metadata.get("short_cues")
    if isinstance(raw, dict):
        return raw
    artifact = context.artifacts.get("short_cues", "")
    return read_json(Path(artifact)) if artifact else {}


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

        def make_commands(encoder: str):
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
        if options.compute_policy == "local":
            final = local_run(options.encoder)
        else:
            try:
                from videoflow.application.compute import router_from_settings

                router = router_from_settings()
                if options.compute_policy == "remote_only":
                    decision = router.decide("short_render")
                    if not decision.is_remote:
                        raise IngestError(
                            "Remote Short render requested but unavailable: "
                            f"{decision.reason}"
                        )
                    commands = make_commands(
                        "nvenc" if options.encoder in {"auto", "nvenc"} else "libx264"
                    )
                    last_commands.append(commands)
                    final = self._remote_render(
                        router, commands, output, options.timeout_sec
                    )
                    placement = decision.execution_node
                    context.metadata["short_render_encoder"] = (
                        "nvenc" if options.encoder in {"auto", "nvenc"} else "libx264"
                    )
                else:
                    def remote_run() -> Path:
                        encoder_name = (
                            "nvenc"
                            if options.encoder in {"auto", "nvenc"}
                            else "libx264"
                        )
                        commands = make_commands(encoder_name)
                        last_commands.append(commands)
                        context.metadata["short_render_encoder"] = encoder_name
                        return self._remote_render(
                            router, commands, output, options.timeout_sec
                        )

                    outcome = router.execute(
                        "short_render",
                        remote_run,
                        lambda: local_run(options.encoder),
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
    ) -> Path:
        result = router.submit(
            "short_render",
            {
                "inputs": [str(path) for path in commands.inputs],
                "params": commands.to_payload(),
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
