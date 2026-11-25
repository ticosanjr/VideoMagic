"""Canonical final audio stage for recipes and manual chains."""

from __future__ import annotations

import json
import math
import os
import shutil
from pathlib import Path
from typing import Any

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
    ducking: bool = True
    music_gain_db: float = Field(default=-18.0, ge=-60.0, le=0.0)
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

    @staticmethod
    def _is_final_path(path: Path) -> bool:
        return path.name.casefold() in {"final.wav", "final_mix.wav", "master.wav"}

    @staticmethod
    def _atomic_copy(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.tmp")
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)

    @staticmethod
    def _sfx_events(context: PipelineContext, *, fps: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        seen: set[tuple[str, float]] = set()

        def add(path: Path, start_sec: float, gain_db: float) -> None:
            key = (str(path), round(start_sec, 6))
            if key in seen:
                return
            seen.add(key)
            events.append(
                {"path": str(path), "start_sec": start_sec, "gain_db": gain_db}
            )

        for relative in ("beat_map.json", "audio/beatmap.json", "audio/sfx-plan.json"):
            payload_path = context.output / relative
            if not payload_path.is_file():
                continue
            try:
                payload = json.loads(payload_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            entries = (
                payload.get("sfx_events")
                or payload.get("sfx")
                or payload.get("cues")
                or []
            )
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                raw = str(entry.get("path") or "").strip()
                if not raw:
                    continue
                path = Path(raw).expanduser()
                if not path.is_absolute():
                    path = context.output / path
                if "start_frame" in entry:
                    start_sec = float(entry.get("start_frame") or 0.0) / max(1.0, fps)
                else:
                    start_sec = float(entry.get("start_sec") or 0.0)
                if entry.get("gain_db") is not None:
                    gain_db = float(entry.get("gain_db") or 0.0)
                else:
                    linear = max(0.0001, float(entry.get("gain") or 0.0))
                    gain_db = 20.0 * math.log10(linear)
                add(path, start_sec, gain_db)
        return events

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = AudioFinalizeParams.model_validate(params)
        media = context.media
        dialogue = context.output / "audio" / "dialogue_timeline.wav"
        dialogue.parent.mkdir(parents=True, exist_ok=True)
        explicit = Path(options.voice_path).expanduser() if options.voice_path else None
        mixed_input = False
        voice: Path
        if explicit is not None and not self._is_final_path(explicit):
            voice = explicit
        elif dialogue.is_file():
            voice = dialogue
        elif (
            context.state is not None
            and context.state.audio_segments
            and context.media is not None
        ):
            from videoflow.exporters.mp4 import export_timeline_audio

            export_timeline_audio(
                context.state,
                dialogue,
                adapter=io.adapter,
            )
            voice = dialogue
        else:
            candidates = [
                context.artifacts.get("audio_mix"),
                context.artifacts.get("audio_master"),
                str(context.output / "audio" / "master.wav"),
            ]
            voice = Path(context.source)
            for value in candidates:
                if not value:
                    continue
                candidate = Path(str(value)).expanduser()
                if candidate.is_file() and not self._is_final_path(candidate):
                    voice = candidate
                    mixed_input = True
                    break
        if not voice.is_file():
            raise ExportError("Audio finalization requires dialogue audio")
        context.artifacts["audio_dialogue"] = str(voice)

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
        fps = 0.0
        if media is not None:
            fps = media.fps_num / max(1, media.fps_den)
        sfx_events: list[dict[str, Any]] = []
        if not mixed_input:
            sfx_events = self._sfx_events(context, fps=fps)
            if options.sfx_path:
                sfx_events.append(
                    {
                        "path": str(Path(options.sfx_path).expanduser()),
                        "start_sec": 0.0,
                        "gain_db": 0.0,
                    }
                )
            legacy_sfx = context.artifacts.get("audio_sfx")
            if legacy_sfx:
                sfx_events.append(
                    {
                        "path": str(Path(str(legacy_sfx)).expanduser()),
                        "start_sec": 0.0,
                        "gain_db": 0.0,
                    }
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
            sfx_path=None,
            sfx_events=sfx_events,
            duration_sec=duration if duration > 0 else None,
            target_lufs=target_lufs,
            true_peak_db=options.true_peak_db,
            sample_rate=options.sample_rate,
            music_gain=options.music_gain,
            sfx_gain=options.sfx_gain,
            ducking=options.ducking,
            music_gain_db=(
                None
                if "music_gain" in options.model_fields_set
                and "music_gain_db" not in options.model_fields_set
                else options.music_gain_db
            ),
            target_name=options.target_name,
        )
        payload = result.to_dict()
        payload["sfx_events_requested"] = len(sfx_events)
        result_path = Path(result.path)
        final_mix = context.output / "audio" / "final_mix.wav"
        final = context.output / "audio" / "final.wav"
        master = context.output / "audio" / "master.wav"
        if result_path != final_mix:
            self._atomic_copy(result_path, final_mix)
        if result_path != final:
            self._atomic_copy(result_path, final)
        if result_path != master:
            self._atomic_copy(result_path, master)
        context.artifacts["audio_final"] = str(result_path)
        context.artifacts["audio_final_mix"] = str(final_mix)
        context.artifacts["audio_mix"] = str(result_path)
        context.artifacts["audio_master"] = str(master)
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
