"""Asset intelligence: shots, semantic matching, beats, and SFX planning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.audio_analysis import detect_beats
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class BeatParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = ""
    tempo_bpm: float = Field(default=120.0, ge=40.0, le=220.0)

@register_step
class MusicBeatStep(BaseStep):
    type = "music.beat"
    title = "Music beats"
    description = "Write a deterministic beat grid for music/SFX placement."
    status = "available"
    icon = "♫"
    color = "#a78bfa"
    params_model = BeatParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = BeatParams.model_validate(params)
        duration = context.duration_samples() / (
            context.media.audio_sample_rate if context.media is not None else 48000
        )
        beats: list[float] = []
        source = "tempo"
        if options.path:
            try:
                beats = detect_beats(Path(options.path).expanduser())
                source = "audio"
            except Exception as exc:
                context.warnings.append(f"Beat detection fell back to tempo: {exc}")
        bpm = options.tempo_bpm
        if len(beats) > 1:
            intervals = [b - a for a, b in zip(beats, beats[1:], strict=False) if b > a]
            if intervals:
                bpm = round(60.0 / (sum(intervals) / len(intervals)), 2)
        if not beats:
            interval = 60.0 / options.tempo_bpm
            current = 0.0
            while current < duration:
                beats.append(round(current, 3))
                current += interval
        target = context.output / "music" / "beats.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {"tempo_bpm": bpm, "source": source, "beats": beats}, indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        context.artifacts["beats"] = str(target)
        context.metadata["beats"] = beats
        io.report(100, f"{len(beats)} beat(s)")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("beats")
        return (Path(path),) if path else ()

class SfxParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    directory: str = ""
    max_per_short: int = Field(default=1, ge=1, le=5)

@register_step
class SfxPlanStep(BaseStep):
    type = "sfx.plan"
    title = "SFX plan"
    description = "Assign local sound effects to Short starts or beats."
    status = "available"
    icon = "♪"
    color = "#f59e0b"
    params_model = SfxParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = SfxParams.model_validate(params)
        directory = (
            Path(options.directory).expanduser()
            if options.directory
            else context.output.parent / "sfx"
        )
        files = (
            sorted(directory.glob("*.wav")) + sorted(directory.glob("*.mp3"))
            if directory.is_dir()
            else []
        )
        plan: dict[str, list[dict[str, Any]]] = {}
        for index, clip in enumerate(context.selected_shorts):
            entries = []
            for offset in range(min(options.max_per_short, len(files))):
                path = files[(index + offset) % len(files)]
                entries.append({"path": str(path), "start_sec": 0.0, "kind": "sfx"})
            plan[clip.title] = entries
        target = context.output / "sfx" / "plan.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        context.artifacts["sfx_plan"] = str(target)
        context.metadata["sfx_plan"] = plan
        io.report(100, f"{sum(len(v) for v in plan.values())} SFX cue(s)")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("sfx_plan")
        return (Path(path),) if path else ()
