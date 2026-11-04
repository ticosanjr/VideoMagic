"""Retake removal and manual transcript overrides."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.retakes import (
    cull_intervals,
    inactive_spans_for_discards,
    snap_cuts_to_silence,
    subtract_spans,
)
from videoflow.application.retakes import (
    cull_retakes as cull_transcript_retakes,
)
from videoflow.application.transcript import normalize_transcript
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError, InvalidRetakeIdsError
from videoflow.domain.state import ManualOverride
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload, require_media
from videoflow.steps.registry import register_step


class RetakesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = ""
    enabled: bool = True
    strategy: Literal["keep_last", "keep_best"] = "keep_last"
    strictness: Literal["conservative", "balanced", "aggressive"] = "balanced"
    context_window: int = Field(default=15, ge=1, le=200)
    normalize: bool = True
    single_pass: bool = True
    max_group_span_seconds: float = Field(default=180.0, ge=15.0, le=600.0)
    max_discard_ratio: float = Field(default=0.45, ge=0.05, le=0.9)
    manual_overrides: list[dict[str, Any]] = Field(default_factory=list)


@register_step
class RetakesStep(BaseStep):
    type = "retakes.cull"
    version = "6"
    title = "Retakes"
    description = (
        "Remove exact repeats and failed takes. Requires a transcript; without "
        "an LLM only exact repetitions are removed."
    )
    requires = ("audio.vad", "transcribe")
    produces = (
        "retake_decisions",
        "retake_spans",
        "normalized_transcript",
        "retakes_report",
    )
    params_model = RetakesParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = RetakesParams.model_validate(params)
        media = require_media(context)
        manual = [ManualOverride.model_validate(item) for item in options.manual_overrides]
        if not context.transcript:
            if manual:
                raise IngestError("Manual transcript overrides require a transcript")
            context.manual_overrides = manual
            context.retake_spans = []
            io.report(100, "No transcript; retakes skipped")
            return

        discard: list[int] = []
        restored: list[int] = []
        overlap_cuts: list[tuple[int, int]] = []
        if options.normalize and not manual:
            normalized = normalize_transcript(
                context.transcript,
                cuts=overlap_cuts,
            )
            if normalized:
                context.transcript = normalized
                context.retake_overlap_cuts = overlap_cuts
                context.metadata["transcript_normalized"] = True
                io.emit(
                    "info",
                    f"Transcript normalized to {len(normalized)} sentence(s)",
                    module="retakes",
                )
        elif options.normalize and manual:
            context.warnings.append(
                "Transcript normalization skipped because manual sentence "
                "overrides refer to the raw transcript."
            )

        if options.enabled:
            io.report(20, "Culling retakes")
            result = cull_transcript_retakes(
                context.transcript,
                client=io.llm_client,
                strategy=options.strategy,  # type: ignore[arg-type]
                context_window=options.context_window,
                strictness=options.strictness,
                single_pass=options.single_pass,
                max_group_span_seconds=options.max_group_span_seconds,
                max_discard_ratio=options.max_discard_ratio,
            )
            discard = list(result.discard_sentence_ids)
            restored = list(result.restored_sentence_ids)
            report = result.to_dict()
            report["overlap_cuts"] = [list(span) for span in overlap_cuts]
            context.metadata["retakes_report"] = report
            io.emit(
                "info",
                f"{len(result.groups)} group(s), {len(discard)} culled, "
                f"{len(restored)} restored",
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

        manual_discard_ids = sorted(
            {item.sentence_id for item in manual if item.action == "discard"}
            & discarded
        )
        context.retake_spans = inactive_spans_for_discards(
            context.transcript, discard, manual_ids=manual_discard_ids
        )
        cuts = cull_intervals(context.transcript, discard)
        cuts, snapped = snap_cuts_to_silence(
            cuts,
            context.silence_spans,
            sample_rate=media.audio_sample_rate,
        )
        context.metadata["retake_cut_snap"] = {
            "cuts": len(cuts),
            "snapped": snapped,
        }
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
            {
                "discard": discard,
                "restored": restored,
                "manual": [m.model_dump() for m in manual],
                "normalized_sentences": len(context.transcript),
                "groups": context.metadata.get("retakes_report", {}).get(
                    "groups", []
                ),
            }
        )
        report = context.metadata.get("retakes_report") or {
            "discard_sentence_ids": discard,
            "restored_sentence_ids": restored,
            "groups": [],
        }
        io.report(
            100,
            f"{len(report.get('groups', []))} group(s), "
            f"{len(discard)} culled, {len(restored)} restored",
        )
