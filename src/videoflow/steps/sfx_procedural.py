"""Procedural, copyright-free SFX synthesis synced to animation curves."""

from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.headless import SfxCue
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class ProceduralSfxParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cues: list[dict[str, object]] = Field(default_factory=list)
    duration_sec: float = Field(default=0.35, gt=0.0, le=10.0)
    sample_rate: int = Field(default=48000, ge=8000, le=192000)
    gain_db: float = Field(default=-6.0, ge=-60.0, le=12.0)


def _tone(kind: str, duration: float, rate: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    count = max(1, int(duration * rate))
    samples: list[float] = []
    for index in range(count):
        t = index / rate
        progress = index / count
        if kind == "click":
            value = math.sin(2 * math.pi * 1800 * t) * math.exp(-progress * 18)
        elif kind == "riser":
            frequency = 180 + 1600 * progress**2
            value = math.sin(2 * math.pi * frequency * t) * progress
        elif kind == "foley":
            value = rng.uniform(-1, 1) * math.exp(-progress * 30)
        else:  # whoosh
            frequency = 900 - 500 * progress
            value = math.sin(2 * math.pi * frequency * t) * math.sin(math.pi * progress)
        samples.append(value)
    return samples


def _write_wav(path: Path, samples: list[float], rate: int, gain_db: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gain = 10 ** (gain_db / 20)
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, value * gain)) * 32767)) for value in samples
    )
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)


@register_step
class ProceduralSfxStep(BaseStep):
    type = "sfx.procedural"
    status = "available"
    icon = "✦"
    color = "#f43f5e"
    title = "Procedural SFX"
    description = "Synthesise whooshes, clicks, risers, and Foley without external samples."
    requires = ()
    produces = ("sfx_cues",)
    params_model = ProceduralSfxParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ProceduralSfxParams.model_validate(params)
        cues: list[SfxCue] = []
        directory = context.work / "sfx"
        directory.mkdir(parents=True, exist_ok=True)
        raw_cues = options.cues or [
            {"kind": "whoosh", "start_sec": 0.0, "duration_sec": options.duration_sec}
        ]
        for index, raw in enumerate(raw_cues):
            kind = str(raw.get("kind") or "whoosh")
            duration = float(raw.get("duration_sec") or options.duration_sec)
            start = float(raw.get("start_sec") or 0.0)
            gain = float(raw.get("gain_db", options.gain_db))
            path = directory / f"{index:02d}-{kind}.wav"
            _write_wav(
                path,
                _tone(kind, duration, options.sample_rate, index + 1),
                options.sample_rate,
                gain,
            )
            cues.append(
                SfxCue(
                    kind=kind if kind in {"whoosh", "click", "riser", "foley"} else "whoosh",
                    start_sec=start,
                    duration_sec=duration,
                    gain_db=gain,
                    path=str(path),
                    sync_to=str(raw.get("sync_to") or ""),
                )
            )
            io.report(
                int((index + 1) / max(1, len(raw_cues)) * 100),
                f"Synthesised {kind}",
            )
        context.metadata["sfx_cues"] = [cue.model_dump(mode="json") for cue in cues]
        context.artifacts["sfx_cues"] = str(directory)
        context.hashes["sfx_procedural"] = str(len(cues))
        io.report(100, f"{len(cues)} procedural cue(s)")
