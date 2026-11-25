"""Editorial cleanup step shared by longform and Shorts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.alignment import refine_transcript
from videoflow.application.editorial_clean import clean_editorial
from videoflow.application.retakes import subtract_spans
from videoflow.application.spans import merge_spans
from videoflow.application.transcript import normalize_transcript
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload, require_media
from videoflow.steps.registry import register_step


class EditorialCleanParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    normalize: bool = True
    semantic: bool = True
    semantic_mode: Literal["inline_llm", "delegated", "off"] = "delegated"
    semantic_block: int = Field(default=8, ge=2, le=32)
    semantic_overlap: int = Field(default=4, ge=0, le=16)
    fuzzy_similarity: float = Field(default=0.52, ge=0.0, le=1.0)
    prefix_similarity: float = Field(default=0.75, ge=0.0, le=1.0)
    max_discard_ratio: float = Field(default=0.75, ge=0.05, le=0.9)
    stutter_gap_sec: float = Field(default=1.2, ge=0.0, le=5.0)
    snap_ms: int = Field(default=60, ge=0, le=250)
    pad_before_ms: int = Field(default=110, ge=0, le=500)
    pad_after_ms: int = Field(default=190, ge=0, le=500)
    crossfade_ms: int = Field(default=15, ge=5, le=100)
    second_pass: bool = True


def apply_editorial_clean(
    context: PipelineContext,
    options: EditorialCleanParams,
    io: StepIO,
) -> dict[str, Any]:
    """Normalize/refine once, run the passes, and persist auditable artifacts."""

    media = require_media(context)
    if not context.transcript:
        report = {
            "schema_version": 1,
            "applied": False,
            "skipped": "no transcript",
            "warnings": [],
        }
        context.metadata["editorial_clean"] = report
        return report
    if context.metadata.get("editorial_clean", {}).get("applied"):
        return dict(context.metadata["editorial_clean"])

    sample_rate = media.audio_sample_rate
    transcript = list(context.transcript)
    pcm_path = _pcm_path(context)

    if options.normalize and not context.metadata.get("transcript_normalized"):
        overlap_cuts: list[tuple[int, int]] = []
        normalized = normalize_transcript(
            transcript,
            sample_rate=sample_rate,
            cuts=overlap_cuts,
            boundary_ids=set(context.discard_sentence_ids),
        )
        if normalized:
            transcript = normalized
            context.transcript = normalized
            context.metadata["transcript_normalized"] = True
        if overlap_cuts:
            context.retake_overlap_cuts = merge_spans(
                [*context.retake_overlap_cuts, *overlap_cuts]
            )

    if context.speech_intervals and not context.metadata.get("alignment"):
        refined, alignment = refine_transcript(
            transcript,
            context.speech_intervals,
            pcm_path=pcm_path,
            sample_rate=sample_rate,
        )
        if refined:
            transcript = refined
            context.transcript = refined
            context.metadata["alignment"] = alignment
            if alignment.get("implausible_before", 0):
                context.warnings.append(
                    "Refined "
                    f"{alignment.get('vad_clamped', 0)} word timing(s); "
                    f"implausible words {alignment['implausible_before']} -> "
                    f"{alignment['implausible_after']}."
                )

    io.report(15, "Cleaning editorial stutters and retakes")
    result = clean_editorial(
        transcript,
        sample_rate=sample_rate,
        pcm_path=pcm_path,
        client=(
            io.llm_client
            if options.semantic and options.semantic_mode == "inline_llm"
            else None
        ),
        semantic=bool(options.semantic and options.semantic_mode != "off"),
        semantic_block=options.semantic_block,
        semantic_overlap=options.semantic_overlap,
        fuzzy_similarity=options.fuzzy_similarity,
        prefix_similarity=options.prefix_similarity,
        max_discard_ratio=options.max_discard_ratio,
        stutter_gap_sec=options.stutter_gap_sec,
        snap_ms=options.snap_ms,
        pad_before_ms=options.pad_before_ms,
        pad_after_ms=options.pad_after_ms,
        crossfade_ms=options.crossfade_ms,
        second_pass=options.second_pass,
    )

    context.transcript = result.working_transcript
    if result.cuts and context.speech_intervals:
        cleaned_speech = subtract_spans(context.speech_intervals, result.cuts)
        if cleaned_speech:
            context.speech_intervals = cleaned_speech
        else:
            context.warnings.append(
                "Editorial cleanup removed every speech span; "
                "the timeline will report the empty result."
            )
    context.discard_sentence_ids = sorted(
        set(context.discard_sentence_ids) | set(result.discarded_sentence_ids)
    )
    for warning in result.report.get("warnings", []):
        context.warnings.append(str(warning))
    context.metadata["editorial_clean"] = result.report
    directory = context.output / "transcript"
    directory.mkdir(parents=True, exist_ok=True)
    candidates = result.report.get("semantic_candidates") or []
    if options.semantic_mode == "delegated":
        candidates_path = directory / "semantic_candidates.json"
        candidates_path.write_text(
            json.dumps(candidates, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        context.artifacts["semantic_candidates"] = str(candidates_path)
        context.metadata["semantic_candidates"] = candidates
    context.metadata["editorial_cuts"] = [list(item) for item in result.cuts]
    context.metadata["speech_pad_before_ms"] = options.pad_before_ms
    context.metadata["speech_pad_after_ms"] = options.pad_after_ms
    context.metadata["editorial_crossfade_ms"] = options.crossfade_ms
    context.hashes["speech.editorial_clean"] = digest_payload(result.report)

    clean_path = directory / "transcript_clean.json"
    report_path = directory / "editorial_clean.json"
    clean_path.write_text(
        json.dumps(
            [item.model_dump(mode="json") for item in result.transcript],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(result.report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    context.artifacts["transcript_clean"] = str(clean_path)
    context.artifacts["editorial_clean"] = str(report_path)
    io.report(
        100,
        f"Editorial cleanup: {result.report['stutters_removed']} stutter(s), "
        f"{len(result.discarded_sentence_ids)} sentence(s), "
        f"{result.report['cut_count']} cut(s)",
    )
    return result.report


def _pcm_path(context: PipelineContext) -> Path | None:
    if context.pcm_path is not None and context.pcm_path.is_file():
        return context.pcm_path
    candidate = context.work / "source.wav"
    return candidate if candidate.is_file() else None


@register_step
class EditorialCleanStep(BaseStep):
    type = "speech.editorial_clean"
    version = "1"
    title = "Editorial cleanup"
    description = (
        "Remove word stutters, false starts, fuzzy and semantic retakes, then "
        "snap cuts to energy valleys before retake culling."
    )
    requires = ("transcribe",)
    produces = ("transcript_clean", "editorial_clean")
    params_model = EditorialCleanParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = EditorialCleanParams.model_validate(params)
        if not options.enabled:
            context.metadata["editorial_clean"] = {
                "schema_version": 1,
                "applied": False,
                "skipped": "disabled",
                "warnings": [],
            }
            io.report(100, "Editorial cleanup disabled")
            return
        apply_editorial_clean(context, options, io)

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("transcript_clean", "editorial_clean")
            if context.artifacts.get(key)
        )


__all__ = ["EditorialCleanParams", "EditorialCleanStep", "apply_editorial_clean"]
