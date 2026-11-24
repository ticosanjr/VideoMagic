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
    finalize_audio,
)
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class AudioFinalizeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_path: str = ""
    music_path: str = ""
    sfx_path: str = ""
    duration_sec: float = Field(default=0.0, ge=0.0, le=24 * 3600)
    target_lufs: float | None = Field(default=None, ge=-30.0, le=-5.0)
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
    produces = ("audio_final",)
    params_model = AudioFinalizeParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = AudioFinalizeParams.model_validate(params)
        media = context.media
        mixed_input = bool(context.artifacts.get("audio_mix")) and not options.voice_path
        timeline_voice = context.work / "audio" / "timeline.wav"
        if (
            not options.voice_path
            and not context.artifacts.get("audio_mix")
            and context.state is not None
            and context.state.audio_segments
            and context.media is not None
        ):
            from videoflow.exporters.mp4 import export_timeline_audio

            timeline_voice.parent.mkdir(parents=True, exist_ok=True)
            export_timeline_audio(
                context.state,
                timeline_voice,
                adapter=io.adapter,
            )
            context.artifacts["audio_timeline"] = str(timeline_voice)
            voice = timeline_voice
            mixed_input = False
        else:
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
            or (
                ""
                if mixed_input
                else (
                    context.artifacts.get("audio_music")
                    or context.artifacts.get("music_bed")
                    or ""
                )
            )
        )
        sfx_value = (
            options.sfx_path
            or ("" if mixed_input else (context.artifacts.get("audio_sfx") or ""))
        )
        duration = options.duration_sec
        if duration <= 0 and media is not None:
            rate = media.audio_sample_rate or 48000
            duration = context.duration_samples() / max(1, rate)
        target_lufs = float(options.target_lufs) if options.target_lufs is not None else None
        if target_lufs is None:
            try:
                from videoflow.application.settings import load_settings

                target_lufs = float(load_settings().quality.target_lufs)
            except Exception:  # noqa: BLE001 - defaults are the contract
                target_lufs = DEFAULT_TARGET_LUFS
        result = finalize_audio(
            voice,
            context.output,
            music_path=music_value or None,
            sfx_path=sfx_value or None,
            duration_sec=duration if duration > 0 else None,
            target_lufs=target_lufs,
            true_peak_db=options.true_peak_db,
            sample_rate=options.sample_rate,
            music_gain=options.music_gain,
            sfx_gain=options.sfx_gain,
            target_name=options.target_name,
        )
        payload = result.to_dict()
        canonical = context.output / "audio" / "master.wav"
        if result.path != canonical:
            import shutil

            canonical.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(result.path, canonical)
        final_mix = context.output / "audio" / "final_mix.wav"
        if Path(result.path) != final_mix:
            import shutil

            final_mix.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(result.path, final_mix)
        context.artifacts["audio_final"] = result.path
        context.artifacts["audio_final_mix"] = str(final_mix)
        context.artifacts["audio_mix"] = result.path
        context.artifacts["audio_master"] = str(canonical)
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
