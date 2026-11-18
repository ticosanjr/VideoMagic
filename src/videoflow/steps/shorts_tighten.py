"""VAD-driven tightening for every selected Short."""

from __future__ import annotations

from dataclasses import replace

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.shorts_tighten import passes_metrics, tighten_clip
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload, require_media
from videoflow.steps.registry import register_step


class TightenParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_pad_ms: int = Field(default=80, ge=0, le=500)
    end_pad_ms: int = Field(default=150, ge=0, le=500)
    max_internal_silence_ms: int = Field(default=500, ge=100, le=2000)
    keep_silence_ms: int = Field(default=150, ge=0, le=500)
    crossfade_ms: int = Field(default=15, ge=0, le=100)
    reject_failed: bool = False


@register_step
class ShortsTightenStep(BaseStep):
    type = "shorts.tighten"
    title = "Tighten Shorts"
    description = (
        "Trim Short edges to the first/last word, remove internal dead air, and "
        "record speech-density metrics used by selection and QA."
    )
    requires = ("shorts.select",)
    produces = ("tightened_shorts",)
    params_model = TightenParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = TightenParams.model_validate(params)
        media = require_media(context)
        if not context.selected_shorts:
            io.report(100, "No Shorts to tighten")
            return
        discard = set(context.discard_sentence_ids)
        words = [
            word
            for sentence in context.transcript
            if sentence.id not in discard
            for word in sentence.words
        ]
        selected = []
        entries = []
        rejected = 0
        total = max(1, len(context.selected_shorts))
        for index, clip in enumerate(context.selected_shorts, start=1):
            tightened = tighten_clip(
                start_sample=clip.start_sample,
                end_sample=clip.end_sample,
                speech_intervals=context.speech_intervals,
                words=words,
                sample_rate=media.audio_sample_rate,
                start_pad_ms=options.start_pad_ms,
                end_pad_ms=options.end_pad_ms,
                max_internal_silence_ms=options.max_internal_silence_ms,
                keep_silence_ms=options.keep_silence_ms,
                crossfade_ms=options.crossfade_ms,
            )
            if options.reject_failed and not passes_metrics(tightened.metrics):
                rejected += 1
                io.report(int(index / total * 100), f"Rejected short {index}/{total}")
                continue
            updated = replace(
                clip,
                start_sample=tightened.start_sample,
                end_sample=tightened.end_sample,
                pieces=tightened.pieces,
            )
            selected.append(updated)
            entry = (
                dict(context.shorts[index - 1])
                if index - 1 < len(context.shorts)
                else clip.to_dict(media.audio_sample_rate)
            )
            entry.update(
                {
                    "start_sample": tightened.start_sample,
                    "end_sample": tightened.end_sample,
                    "pieces": [list(piece) for piece in tightened.pieces],
                    **tightened.metrics,
                }
            )
            entries.append(entry)
            io.report(int(index / total * 100), f"Tightened {index}/{total}")
        context.selected_shorts = selected
        context.shorts = entries
        context.metadata["tighten"] = {
            "processed": len(selected),
            "rejected": rejected,
            "metrics": [entry for entry in entries],
        }
        context.hashes["shorts.tighten"] = digest_payload(context.metadata["tighten"])
        io.report(100, f"{len(selected)} Short(s) tightened")


__all__ = ["ShortsTightenStep"]
