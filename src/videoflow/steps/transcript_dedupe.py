"""Clean transcript repetitions and persist raw/clean audit artifacts."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict

from videoflow.application.transcript_clean import clean_transcript
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload, require_media
from videoflow.steps.registry import register_step


class DedupeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


@register_step
class TranscriptDedupeStep(BaseStep):
    type = "transcript.dedupe"
    title = "Clean transcript"
    description = (
        "Mark low-confidence words and remove immediate low-confidence repetitions "
        "before retake culling and caption planning."
    )
    requires = ("transcribe",)
    produces = ("transcript_clean", "transcript_raw")
    params_model = DedupeParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        media = require_media(context)
        if not context.transcript:
            io.report(100, "No transcript to clean")
            return
        raw = [sentence.model_dump(mode="json") for sentence in context.transcript]
        cleaned, report = clean_transcript(
            context.transcript, sample_rate=media.audio_sample_rate
        )
        context.transcript = cleaned
        directory = context.output / "transcript"
        directory.mkdir(parents=True, exist_ok=True)
        raw_path = directory / "transcript_raw.json"
        clean_path = directory / "transcript_clean.json"
        raw_path.write_text(
            json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        clean_path.write_text(
            json.dumps(
                [item.model_dump(mode="json") for item in cleaned],
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        context.artifacts["transcript_raw"] = str(raw_path)
        context.artifacts["transcript_clean"] = str(clean_path)
        context.hashes["transcript.dedupe"] = digest_payload(report)
        context.metadata["transcript_clean"] = report
        io.report(100, f"Transcript cleaned ({report['removed_repetitions']} repetitions removed)")


__all__ = ["TranscriptDedupeStep"]
