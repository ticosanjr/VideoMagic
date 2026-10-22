"""Retake removal and manual transcript overrides."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.retakes import (
    cull_intervals,
    subtract_spans,
)
from videoflow.application.retakes import (
    cull_retakes as cull_transcript_retakes,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError, InvalidRetakeIdsError
from videoflow.domain.state import ManualOverride
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload, require_media
from videoflow.steps.registry import register_step


class RetakesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    strategy: str = "keep_last"
    strictness: str = "balanced"
    context_window: int = Field(default=15, ge=1, le=200)
    manual_overrides: list[dict[str, Any]] = Field(default_factory=list)


@register_step
class RetakesStep(BaseStep):
    type = "retakes.cull"
    title = "Retakes"
    description = "Remove exact repeats and failed takes, then apply manual overrides."
    requires = ("audio.vad", "transcribe")
    produces = ("retake_decisions",)
    params_model = RetakesParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = RetakesParams.model_validate(params)
        media = require_media(context)
        manual = [ManualOverride.model_validate(item) for item in options.manual_overrides]
        if not context.transcript:
            if manual:
                raise IngestError("Manual transcript overrides require a transcript")
            context.manual_overrides = manual
            io.report(100, "No transcript; retakes skipped")
            return

        discard: list[int] = []
        restored: list[int] = []
        if options.enabled:
            io.report(20, "Culling retakes")
            result = cull_transcript_retakes(
                context.transcript,
                client=io.llm_client,
                strategy=options.strategy,  # type: ignore[arg-type]
                context_window=options.context_window,
                strictness=options.strictness,
            )
            discard = list(result.discard_sentence_ids)
            restored = list(result.restored_sentence_ids)
            io.emit(
                "info",
                f"{len(discard)} culled, {len(restored)} restored",
                module="retakes",
            )

        valid = {item.id for item in context.transcript}
        unknown = [item.sentence_id for item in manual if item.sentence_id not in valid]
        if unknown:
            raise InvalidRetakeIdsError(unknown)
        discarded = set(discard)
        for item in manual:
            if item.action == "discard":
                discarded.add(item.sentence_id)
            else:
                discarded.discard(item.sentence_id)
        discard = sorted(discarded)

        cuts = cull_intervals(context.transcript, discard)
        speech = subtract_spans(context.speech_intervals, cuts)
        minimum_ms = int(context.metadata.get("min_speech_ms", 100))
        minimum = max(1, (minimum_ms * media.audio_sample_rate + 500) // 1000)
        speech = [(start, end) for start, end in speech if end - start >= minimum]
        if not speech:
            raise IngestError("Culling and overrides removed all speech")

        context.speech_intervals = speech
        context.discard_sentence_ids = discard
        context.restored_sentence_ids = restored
        context.manual_overrides = manual
        context.hashes["retakes"] = digest_payload(
            {"discard": discard, "restored": restored, "manual": [m.model_dump() for m in manual]}
        )
        io.report(100, f"{len(discard)} culled, {len(restored)} restored")
