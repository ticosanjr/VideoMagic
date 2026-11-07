"""Audio-visual drift correction for transcripts."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.errors import RecipeError
from videoflow.domain.state import Sentence, WordTiming
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class DriftParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offset_ms: float = Field(default=200.0, ge=0.0, le=2000.0)
    min_ms: float = Field(default=0.0, ge=0.0, le=2000.0)
    max_ms: float = Field(default=2000.0, ge=0.0, le=5000.0)


@register_step
class DriftCorrectionStep(BaseStep):
    type = "edit.drift"
    title = "Drift correction"
    description = (
        "Shift transcript timestamps by the camera/audio buffer offset so cuts "
        "and captions stay in sync."
    )
    status = "available"
    icon = "↔"
    color = "#38bdf8"
    requires = ("transcribe",)
    produces = ("transcript", "drift_report")
    params_model = DriftParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = DriftParams.model_validate(params)
        if not options.min_ms <= options.offset_ms <= options.max_ms:
            raise RecipeError(
                f"drift offset {options.offset_ms} ms is outside "
                f"[{options.min_ms}, {options.max_ms}]"
            )
        if not context.transcript:
            context.metadata["drift_correction"] = {"applied": False, "reason": "no transcript"}
            io.report(100, "No transcript; drift skipped")
            return
        sample_rate = (
            context.media.audio_sample_rate if context.media is not None else 48_000
        )
        offset = round(options.offset_ms * sample_rate / 1000)
        adjusted = 0
        clamped = 0
        corrected: list[Sentence] = []
        for sentence in context.transcript:
            words: list[WordTiming] = []
            for word in sentence.words:
                start = max(0, word.start_sample - offset)
                end = max(start, word.end_sample - offset)
                if start != word.start_sample or end != word.end_sample:
                    adjusted += 1
                if word.start_sample - offset < 0:
                    clamped += 1
                words.append(
                    WordTiming(
                        word=word.word,
                        start_sample=start,
                        end_sample=end,
                        probability=word.probability,
                    )
                )
            start = max(0, sentence.start_sample - offset)
            end = max(start, sentence.end_sample - offset)
            corrected.append(
                Sentence(
                    id=sentence.id,
                    start_sample=start,
                    end_sample=end,
                    text=sentence.text,
                    speaker=sentence.speaker,
                    words=words,
                )
            )
        context.transcript = corrected
        report = {
            "applied": True,
            "offset_ms": options.offset_ms,
            "offset_samples": offset,
            "sentences": len(corrected),
            "words_adjusted": adjusted,
            "clamped_at_zero": clamped,
        }
        context.metadata["drift_correction"] = report
        target = context.output / "alignment" / "drift.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        context.artifacts["drift_report"] = str(target)
        context.hashes["edit.drift"] = digest_payload(report)
        if clamped:
            context.warnings.append(
                f"Drift correction clamped {clamped} word(s) at zero."
            )
        io.report(100, f"Applied {options.offset_ms:.0f} ms drift correction")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("drift_report")
        return (Path(path),) if path else ()
