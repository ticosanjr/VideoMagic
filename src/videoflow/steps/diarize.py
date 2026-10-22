"""Lightweight speaker-turn labeling for speaker-colored captions.

This is intentionally a heuristic, not a diarization model: a pause longer than
the configured threshold starts a new speaker turn. It gives the caption step a
stable speaker id without downloading a diarization model.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class DiarizeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["heuristic", "none"] = "heuristic"
    pause_ms: int = Field(default=400, ge=50, le=5000)
    max_speakers: int = Field(default=4, ge=1, le=12)


@register_step
class DiarizeStep(BaseStep):
    type = "audio.diarize"
    title = "Speaker turns"
    description = (
        "Assign heuristic speaker ids by pause length for speaker-colored captions."
    )
    requires = ("transcribe",)
    produces = ("speaker_turns",)
    params_model = DiarizeParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = DiarizeParams.model_validate(params)
        if not context.transcript:
            raise IngestError("Speaker turns require a transcript.")
        if options.method == "none":
            io.report(100, "Speaker turns disabled")
            return
        media = context.media
        sample_rate = media.audio_sample_rate if media is not None else 48000
        pause = max(1, round(options.pause_ms * sample_rate / 1000))
        speaker = 0
        previous_end: int | None = None
        updated = []
        for sentence in sorted(context.transcript, key=lambda item: item.start_sample):
            if previous_end is not None and sentence.start_sample - previous_end >= pause:
                speaker = (speaker + 1) % options.max_speakers
            updated.append(sentence.model_copy(update={"speaker": speaker}))
            previous_end = sentence.end_sample
        context.transcript = updated
        context.metadata["speaker_count"] = len({item.speaker for item in updated})
        context.hashes["diarize"] = digest_payload(
            [(item.id, item.speaker) for item in updated]
        )
        io.emit("info", f"{context.metadata['speaker_count']} speaker turns", module="diarize")
        io.report(100, "Speaker turns ready")
