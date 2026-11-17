"""Content-cycle steps.

Implemented steps do real work. Planned steps are intentionally no-ops; the
runner marks them as skipped so a recipe can model the full workflow without
pretending a missing engine ran.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.audio import audio_filters
from videoflow.core.context import PipelineContext
from videoflow.domain.config import AudioEnhanceConfig
from videoflow.domain.errors import ExportError, IngestError
from videoflow.exporters.mp4 import export_timeline_audio
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class AudioMasterParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    highpass_hz: int = Field(default=80, ge=20, le=500)
    denoise: bool = True
    denoise_db: int = Field(default=12, ge=0, le=40)
    noise_floor_db: int = Field(default=-30, ge=-80, le=0)
    loudnorm: bool = True
    target_lufs: float = Field(default=-16.0, ge=-30.0, le=-5.0)
    true_peak_db: float = Field(default=-1.5, ge=-9.0, le=0.0)
    sample_rate: int = Field(default=48000, ge=8000, le=192000)
    platform: Literal["youtube", "tiktok", "reels", "shorts", "podcast"] = "youtube"
    source: Literal["auto", "timeline", "source"] = "auto"


class AudioQaParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_lufs: float = Field(default=-16.0, ge=-30.0, le=-5.0)
    tolerance_lu: float = Field(default=2.0, ge=0.0, le=10.0)
    max_true_peak_db: float = Field(default=-1.0, ge=-20.0, le=0.0)


@register_step
class AudioMasterStep(BaseStep):
    type = "audio.master"
    title = "Audio master"
    description = "High-pass, denoise, and normalise the dialogue bed with EBU R128 loudness."
    status = "available"
    icon = "♫"
    color = "#a78bfa"
    requires = ("ingest",)
    produces = ("audio_master",)
    params_model = AudioMasterParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = AudioMasterParams.model_validate(params)
        if context.media is None:
            raise IngestError("Audio master requires ingested media.")
        target_lufs = options.target_lufs
        if options.platform in {"tiktok", "reels", "shorts"} and options.target_lufs == -16.0:
            target_lufs = -16.5
        filters = audio_filters(
            AudioEnhanceConfig(
                enabled=True,
                highpass_hz=options.highpass_hz,
                denoise=options.denoise,
                denoise_db=options.denoise_db,
                noise_floor_db=options.noise_floor_db,
                loudnorm=options.loudnorm,
                target_lufs=target_lufs,
                true_peak_db=options.true_peak_db,
            )
        )
        target = context.output / "audio" / "master.wav"
        has_timeline = bool(context.state is not None and context.state.audio_segments)
        use_timeline = options.source == "timeline" or (options.source == "auto" and has_timeline)
        if use_timeline and context.state is None:
            raise ExportError("Audio master requested the timeline, but no timeline exists.")
        adapter = (
            io.adapter
            if getattr(io.adapter, "render", None) is not None
            else FFmpegAdapter(cancel_event=io.cancel_event)
        )
        if use_timeline:
            export_timeline_audio(
                context.state,  # type: ignore[arg-type]
                target,
                adapter=adapter,
                audio_filters=filters,
                sample_rate=options.sample_rate,
            )
        else:
            if has_timeline and options.source == "source":
                context.warnings.append("Audio master used the source because source='source'.")
            adapter.master_audio(
                context.source,
                target,
                filters=filters,
                sample_rate=options.sample_rate,
            )
        context.artifacts["audio_master"] = str(target)
        context.metadata["audio_master_filters"] = filters
        filters_path = context.output / "audio" / "master-filters.json"
        filters_path.write_text(json.dumps({"filters": filters}, indent=2) + "\n", encoding="utf-8")
        context.artifacts["audio_master_filters"] = str(filters_path)
        io.report(100, "Audio master ready")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("audio_master")
        return (Path(path),) if path else ()


@register_step
class AudioQaStep(BaseStep):
    type = "audio.qa"
    title = "Audio QA"
    description = "Measure EBU R128 integrated loudness and true peak for delivery."
    status = "available"
    icon = "◉"
    color = "#22c55e"
    produces = ("audio_qa",)
    params_model = AudioQaParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = AudioQaParams.model_validate(params)
        try:
            from videoflow.application.settings import load_settings

            quality = load_settings().quality
            if options.target_lufs == -16.0:
                options = options.model_copy(update={"target_lufs": quality.target_lufs})
            if options.max_true_peak_db == -1.0:
                options = options.model_copy(update={"max_true_peak_db": quality.true_peak_db})
        except Exception:
            pass
        master = context.artifacts.get("audio_mix") or context.artifacts.get("audio_master")
        source = Path(master) if master else Path(context.source)
        if not source.is_file():
            raise IngestError("Audio QA requires a rendered audio mix or ingested media.")
        measurement = FFmpegAdapter().measure_loudness(source)
        lufs = float(measurement["integrated_lufs"])
        peak = float(measurement["true_peak_dbfs"])
        passed = (
            abs(lufs - options.target_lufs) <= options.tolerance_lu
            and peak <= options.max_true_peak_db
        )
        payload = {
            "ok": True,
            "source": str(source),
            "integrated_lufs": lufs,
            "true_peak_dbfs": peak,
            "target_lufs": options.target_lufs,
            "max_true_peak_db": options.max_true_peak_db,
            "passed": passed,
        }
        target = context.output / "audio" / "qa.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        context.artifacts["audio_qa"] = str(target)
        context.metadata["audio_qa"] = payload
        if not passed:
            context.warnings.append(f"Audio QA out of spec: {lufs:.1f} LUFS, peak {peak:.1f} dBFS")
        io.report(100, f"{lufs:.1f} LUFS · peak {peak:.1f} dBFS")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("audio_qa")
        return (Path(path),) if path else ()
