"""Sidechain music ducking for the master audio bed."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ExportError
from videoflow.runtime import find_binary
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class DuckParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    music_path: str = ""
    duck_db: float = Field(default=-12.0, ge=-40.0, le=0.0)
    threshold: float = Field(default=0.015, gt=0.0, le=1.0)
    ratio: float = Field(default=8.0, ge=1.0, le=20.0)
    attack_ms: int = Field(default=20, ge=1, le=500)
    release_ms: int = Field(default=300, ge=10, le=2000)
    music_gain: float = Field(default=0.4, ge=0.0, le=1.0)
    output_name: str = "master_mix.wav"


@register_step
class AudioDuckStep(BaseStep):
    type = "audio.duck"
    title = "Music ducking"
    description = (
        "Attenuate a music bed under dialogue with FFmpeg sidechain compression."
    )
    status = "available"
    icon = "♫"
    color = "#a78bfa"
    requires = ("audio.master",)
    produces = ("audio_mix",)
    params_model = DuckParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = DuckParams.model_validate(params)
        dialogue = context.artifacts.get("audio_master")
        dialogue_path = (
            Path(dialogue) if dialogue else context.output / "audio" / "master.wav"
        )
        if not dialogue_path.is_file():
            raise ExportError("Music ducking requires an audio master")
        music = Path(options.music_path).expanduser() if options.music_path else None
        report: dict[str, object] = {
            "applied": False,
            "dialogue": str(dialogue_path),
            "music": str(music) if music else "",
            "duck_db": options.duck_db,
            "threshold": options.threshold,
            "ratio": options.ratio,
        }
        if music is None or not music.is_file():
            report["reason"] = "no music bed configured"
            context.metadata["audio_duck"] = report
            context.warnings.append(
                "Music ducking skipped: no music bed configured."
            )
            self._write(context, report)
            io.report(100, "No music bed; ducking skipped")
            return
        target = context.output / "audio" / options.output_name
        target.parent.mkdir(parents=True, exist_ok=True)
        gain = max(0.0, min(1.0, options.music_gain))
        filter_complex = (
            f"[1:a][0:a]sidechaincompress=threshold={options.threshold}:"
            f"ratio={options.ratio}:attack={options.attack_ms}:"
            f"release={options.release_ms}[ducked];"
            f"[0:a][ducked]amix=inputs=2:weights=1.0 {gain:.3f}[out]"
        )
        command = [
            str(find_binary("ffmpeg")),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(dialogue_path),
            "-i",
            str(music),
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s16le",
            str(target),
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0:
            raise ExportError(
                "Music ducking failed: "
                + (completed.stderr.strip() or f"exit {completed.returncode}")
            )
        report["applied"] = True
        report["output"] = str(target)
        report["gain"] = gain
        context.artifacts["audio_mix"] = str(target)
        # QA and sidecars should measure the final mix.
        context.artifacts["audio_master"] = str(target)
        context.metadata["audio_duck"] = report
        context.hashes["audio.duck"] = digest_payload(report)
        self._write(context, report)
        io.report(100, f"Music ducked by {abs(options.duck_db):.0f} dB")

    @staticmethod
    def _write(context: PipelineContext, report: dict[str, object]) -> None:
        target = context.output / "audio" / "duck.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        context.artifacts["audio_duck"] = str(target)

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("audio_duck")
        return (Path(path),) if path else ()
