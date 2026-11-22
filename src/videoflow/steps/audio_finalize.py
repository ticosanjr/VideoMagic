"""Canonical final audio stage for recipes and manual chains."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ExportError
from videoflow.domains.audio.finalize import (
    DEFAULT_MUSIC_GAIN,
    DEFAULT_SFX_GAIN,
    DEFAULT_TARGET_LUFS,
    DEFAULT_TRUE_PEAK_DB,
    TARGET_LUFS,
    finalize_audio,
)
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload, require_media
from videoflow.steps.registry import register_step


class AudioFinalizeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_path: str = ""
    music_path: str = ""
    sfx_path: str = ""
    duration_sec: float = Field(default=0.0, ge=0.0, le=24 * 3600)
    target_lufs: float = Field(default=DEFAULT_TARGET_LUFS, ge=-30.0, le=-5.0)
    true_peak_db: float = Field(default=DEFAULT_TRUE_PEAK_DB, ge=-9.0, le=0.0)
    sample_rate: int = Field(default=48_000, ge=8_000, le=192_000)
    music_gain: float = Field(default=DEFAULT_MUSIC_GAIN, ge=0.0, le=1.0)
    sfx_gain: float = Field(default=DEFAULT_SFX_GAIN, ge=0.0, le=1.0)
    target_name: str = Field(default="final.wav", max_length=120)


@register_step
class AudioFinalizeStep(BaseStep):
    type = "audio.finalize"
    title = "Finalize audio"
    description = (
        "Clean dialogue, repair a left/right mono imbalance, mix music and Foley, "
        "apply two-pass EBU R128 loudness, and write 48 kHz/24-bit final.wav."
    )
    status = "available"
    icon = "♫"
    color = "#a78bfa"
    requires = ("ingest",)
    produces = ("audio_final",)
    params_model = AudioFinalizeParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = AudioFinalizeParams.model_validate(params)
        media = require_media(context)
        voice_value = (
            options.voice_path
            or context.artifacts.get("audio_mix")
            or context.artifacts.get("audio_master")
            or str(context.output / "audio" / "master.wav")
        )
        voice = Path(voice_value).expanduser()
        if not voice.is_file():
            voice = Path(context.source)
        if not voice.is_file():
            raise ExportError("Audio finalization requires dialogue audio")
        music_value = (
            options.music_path
            or context.artifacts.get("audio_music")
            or context.artifacts.get("music_bed")
            or ""
        )
        sfx_value = options.sfx_path or context.artifacts.get("audio_sfx") or ""
        duration = options.duration_sec
        if duration <= 0:
            rate = media.audio_sample_rate or 48000
            duration = context.duration_samples() / max(1, rate)
        target_lufs = TARGET_LUFS
        if abs(float(options.target_lufs) - TARGET_LUFS) > 0.01:
            context.warnings.append(
                f"audio.finalize enforced {TARGET_LUFS:g} LUFS instead of "
                f"{options.target_lufs:g} LUFS"
            )
        result = finalize_audio(
            voice,
            context.output,
            music_path=music_value or None,
            sfx_path=sfx_value or None,
            duration_sec=duration,
            target_lufs=target_lufs,
            true_peak_db=options.true_peak_db,
            sample_rate=options.sample_rate,
            music_gain=options.music_gain,
            sfx_gain=options.sfx_gain,
            target_name=options.target_name,
        )
        payload = result.to_dict()
        context.artifacts["audio_final"] = result.path
        context.artifacts["audio_mix"] = result.path
        context.metadata["audio_finalize"] = payload
        context.hashes["audio.finalize"] = digest_payload(payload)
        target = context.output / "audio" / "finalize.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        context.artifacts["audio_finalize"] = str(target)
        for warning in result.warnings:
            context.warnings.append(warning)
        io.report(100, f"Audio final: {result.integrated_lufs:.1f} LUFS")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        paths = [
            Path(context.artifacts[key])
            for key in ("audio_final", "audio_finalize")
            if context.artifacts.get(key)
        ]
        return tuple(paths)


__all__ = ["AudioFinalizeParams", "AudioFinalizeStep"]
