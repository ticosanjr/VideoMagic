"""Retake removal and manual transcript overrides."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.alignment import refine_transcript
from videoflow.application.retakes import (
    apply_manual_overrides,
    cull_intervals,
    inactive_spans_for_discards,
    snap_cuts_to_silence,
    subtract_spans,
)
from videoflow.application.retakes import (
    cull_retakes as cull_transcript_retakes,
)
from videoflow.application.spans import merge_spans
from videoflow.application.transcript import normalize_transcript
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError, MissingPrerequisiteError
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
    max_group_span_seconds: float = Field(default=420.0, ge=15.0, le=1800.0)
    max_discard_ratio: float = Field(default=0.75, ge=0.05, le=0.9)
    semantic_duplicates: bool = False
    editorial_clean: bool = True
    editorial_semantic: bool = True
    manual_overrides: list[dict[str, Any]] = Field(default_factory=list)
    use_profile: bool = False


@register_step
class RetakesStep(BaseStep):
    type = "retakes.cull"
    version = "9"
    title = "Retakes"
    description = (
        "Run editorial cleanup, then remove exact repeats and failed takes. "
        "Without an LLM only deterministic passes are used."
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
        if options.use_profile:
            profile = context.metadata.get("decoupage_profile")
            if isinstance(profile, dict) and profile.get("available"):
                recommended = str(profile.get("recommended_strictness") or "")
                if (
                    recommended in {"conservative", "balanced", "aggressive"}
                    and recommended != options.strictness
                ):
                    context.warnings.append(
                        "Retake strictness calibrated from the reference edit: "
                        f"{options.strictness} -> {recommended}."
                    )
                    options = options.model_copy(update={"strictness": recommended})
        media = require_media(context)
        manual = [ManualOverride.model_validate(item) for item in options.manual_overrides]
        if not context.transcript:
            if manual:
                raise IngestError("Manual transcript overrides require a transcript")
            context.manual_overrides = manual
            context.retake_spans = []
            io.report(100, "No transcript; retakes skipped")
            return
        if not context.speech_intervals:
            raise MissingPrerequisiteError(
                "retakes.cull requires VAD speech intervals",
                fix_hint=(
                    "Execute audio.vad antes de retakes.cull ou use "
                    "vf_decupage(action='run_full')."
                ),
            )

        discard: list[int] = list(context.discard_sentence_ids)
        restored: list[int] = []
        overlap_cuts: list[tuple[int, int]] = []
        already_editorial = bool(
            context.metadata.get("editorial_clean", {}).get("applied")
        )
        if options.normalize and not manual and not already_editorial:
            normalized = normalize_transcript(
                context.transcript,
                cuts=overlap_cuts,
                boundary_ids=set(context.discard_sentence_ids),
            )
            if normalized:
                context.transcript = normalized
                context.retake_overlap_cuts = merge_spans(
                    [*context.retake_overlap_cuts, *overlap_cuts]
                )
                context.metadata["transcript_normalized"] = True
                io.emit(
                    "info",
                    f"Transcript normalized to {len(normalized)} sentence(s)",
                    module="retakes",
                )
        elif options.normalize and manual and not already_editorial:
            context.warnings.append(
                "Transcript normalization skipped because manual sentence "
                "overrides refer to the raw transcript."
            )

        pcm_path = context.pcm_path
        if pcm_path is None or not pcm_path.is_file():
            candidate = context.work / "source.wav"
            pcm_path = candidate if candidate.is_file() else None
        if not context.metadata.get("alignment"):
            refined, alignment = refine_transcript(
                context.transcript,
                context.speech_intervals,
                pcm_path=pcm_path,
                sample_rate=media.audio_sample_rate,
            )
            if refined:
                context.transcript = refined
                context.metadata["alignment"] = alignment
                if alignment.get("implausible_before", 0):
                    context.warnings.append(
                        "Refined "
                        f"{alignment.get('vad_clamped', 0)} word timing(s); "
                        f"implausible words {alignment['implausible_before']} -> "
                        f"{alignment['implausible_after']}."
                    )

        if options.editorial_clean and not already_editorial:
            from videoflow.steps.editorial_clean import (
                EditorialCleanParams,
                apply_editorial_clean,
            )

            apply_editorial_clean(
                context,
                EditorialCleanParams(
                    normalize=not manual,
                    semantic=options.editorial_semantic,
                ),
                io,
            )
            discard = list(context.discard_sentence_ids)

        if options.enabled:
            io.report(20, "Culling retakes")
            candidates = [
                item
                for item in context.transcript
                if item.id not in set(context.discard_sentence_ids)
            ]
            result = cull_transcript_retakes(
                candidates,
                client=io.llm_client,
                strategy=options.strategy,
                context_window=options.context_window,
                strictness=options.strictness,
                single_pass=options.single_pass,
                max_group_span_seconds=options.max_group_span_seconds,
                max_discard_ratio=options.max_discard_ratio,
                semantic_duplicates=options.semantic_duplicates,
            )
            discard = sorted(
                set(context.discard_sentence_ids) | set(result.discard_sentence_ids)
            )
            restored = list(result.restored_sentence_ids)
            report = result.to_dict()
            report["overlap_cuts"] = [
                [span[0], span[1]] for span in context.retake_overlap_cuts
            ]
            report["editorial_clean"] = dict(
                context.metadata.get("editorial_clean") or {}
            )
            context.metadata["retakes_report"] = report
            io.emit(
                "info",
                f"{len(result.groups)} group(s), {len(discard)} culled, "
                f"{len(restored)} restored",
                module="retakes",
            )

        valid = {item.id for item in context.transcript}
        discard, manual_discard_ids = apply_manual_overrides(discard, manual, valid)
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
                "editorial": context.metadata.get("editorial_clean", {}),
                "groups": context.metadata.get("retakes_report", {}).get(
                    "groups", []
                ),
            }
        )
        transcript_dir = context.output / "transcript"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        kept = [item for item in context.transcript if item.id not in discard]
        clean_path = transcript_dir / "transcript_clean.json"
        clean_path.write_text(
            json.dumps(
                [item.model_dump(mode="json") for item in kept],
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        context.artifacts["transcript_clean"] = str(clean_path)
        final_report: dict[str, Any] = context.metadata.get("retakes_report") or {
            "discard_sentence_ids": discard,
            "restored_sentence_ids": restored,
            "groups": [],
        }
        io.report(
            100,
            f"{len(final_report.get('groups', []))} group(s), "
            f"{len(discard)} culled, {len(restored)} restored",
        )
