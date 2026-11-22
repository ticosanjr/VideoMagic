"""Timeline construction step."""

from __future__ import annotations

import array
import contextlib
import math
import wave
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from videoflow.application.boundaries import enforce_word_integrity
from videoflow.application.non_speech import load_pcm_mono
from videoflow.application.retakes import subtract_spans
from videoflow.application.silence import cap_silence_spans, detect_silence_spans
from videoflow.application.timeline_builder import (
    add_untranscribed_spans,
    build_inactive_segments,
    build_timeline,
    detect_noise_spans,
    exclude_removed_audio,
    repair_clipped_words,
    transcript_spans,
)
from videoflow.application.vad import pad_spans
from videoflow.application.word_cuts import plan_word_cuts
from videoflow.core.context import PipelineContext
from videoflow.domain.config import JlCutsConfig, ZoomsConfig
from videoflow.domain.state import InactiveSpan, ProjectState, SampleSpan
from videoflow.domains.audio.events import detect_audio_events, load_model
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload, require_media
from videoflow.steps.registry import register_step


class TimelineParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cut_mode: Literal["custom", "hard", "j_cut", "l_cut"] = "custom"
    enable_j_cuts: bool = True
    enable_l_cuts: bool = False
    offset_ms: int = Field(default=200, ge=100, le=500)
    audio_crossfade_ms: int = Field(default=20, ge=10, le=50)
    fade_in_ms: int = Field(default=20, ge=0, le=1000)
    fade_out_ms: int = Field(default=20, ge=0, le=1000)
    fade_curve: Literal["linear", "logarithmic"] = "logarithmic"
    handle_check: bool = True

    zoom_mode: Literal["alternate_cuts", "topic_change", "manual_rules"] = "alternate_cuts"
    zoom_min_scale: float = Field(default=1.0, ge=1.0, le=4.0)
    zoom_max_scale: float = Field(default=1.5, ge=1.0, le=4.0)
    punch_in_scale: float = Field(default=1.15, ge=1.0, le=4.0)
    anchor_point: Literal["center", "upper_third", "face_detect"] = "upper_third"
    progressive_zoom: bool = False
    pan_direction: Literal["none", "left_to_right", "right_to_left"] = "none"

    pad_before_ms: int | None = Field(default=20, ge=0)
    pad_after_ms: int | None = Field(default=40, ge=0)
    head_guard_ms: int = Field(default=80, ge=0, le=500)
    tail_guard_ms: int = Field(default=200, ge=0, le=800)
    final_tail_guard_ms: int = Field(default=500, ge=400, le=800)
    guard_energy_threshold: int = Field(default=800, ge=0)
    max_internal_gap_ms: int = Field(default=150, ge=0, le=2000)
    internal_gap_mode: Literal["smart", "all", "silence"] = "smart"
    gap_energy_threshold: int = Field(default=800, ge=0)
    long_gap_ms: int = Field(default=800, ge=0)
    max_silence_ms: int = Field(default=500, ge=0, le=10000)
    keep_silence_ms: int = Field(default=300, ge=0, le=5000)
    silence_threshold_db: float = Field(default=-35.0, ge=-80.0, le=0.0)
    silence_frame_ms: int = Field(default=10, ge=1, le=100)
    silence_word_margin_ms: int = Field(default=20, ge=0, le=200)
    repair_word_tails: bool = False
    word_repair_max_ms: int = Field(default=800, ge=100, le=5000)
    word_integrity_max_ms: int = Field(default=1500, ge=100, le=5000)
    word_integrity_gap_ms: int = Field(default=500, ge=0, le=2000)
    min_clip_ms: int = Field(default=200, ge=1, le=5000)
    drop_isolated_words: bool = True
    detect_repeats: bool = True
    remove_fillers: bool = False
    repeat_min_words: int = Field(default=5, ge=2, le=20)
    repeat_max_gap_seconds: float = Field(default=180.0, ge=1.0, le=3600.0)
    repeat_gap_seconds: float = Field(default=1.2, ge=0.1, le=10.0)
    repeat_pad_ms: int = Field(default=40, ge=0, le=500)
    word_cut_max_ratio: float = Field(default=0.9, ge=0.0, le=1.0)
    keep_untranscribed: bool = True
    untranscribed_min_ms: int = Field(default=500, ge=100, le=5000)
    untranscribed_energy_threshold: int = Field(default=800, ge=0)
    remove_impulsive_noise: bool = True
    impulsive_noise_min_ms: int = Field(default=40, ge=10, le=1000)
    impulsive_noise_max_ms: int = Field(default=600, ge=40, le=5000)
    impulsive_noise_margin_ms: int = Field(default=80, ge=0, le=500)
    use_audio_event_model: bool = False
    use_ast_audio_tagger: bool = True
    ast_noise_threshold: float = Field(default=0.1, ge=0.0, le=1.0)
    use_transcript_spans: bool = True
    noise_filter: Literal["off", "non_speech", "non_speech_and_nonlexical"] = (
        "non_speech"
    )
    noise_min_ms: int = Field(default=180, ge=0, le=5000)
    noise_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    transition_frames: int = Field(default=0, ge=0, le=120)
    transition_type: Literal["crossfade", "fade_to_black"] = "crossfade"
    project_id: str | None = None
    revision: int = Field(default=1, ge=1)
    replace_manual: bool = True

    @model_validator(mode="after")
    def resolve_cut_mode(self) -> TimelineParams:
        if self.cut_mode == "hard":
            self.enable_j_cuts = False
            self.enable_l_cuts = False
        elif self.cut_mode == "j_cut":
            self.enable_j_cuts = True
            self.enable_l_cuts = False
        elif self.cut_mode == "l_cut":
            self.enable_j_cuts = False
            self.enable_l_cuts = True
        return self


def _pcm_path(context: PipelineContext) -> Path | None:
    if context.pcm_path is not None and context.pcm_path.is_file():
        return context.pcm_path
    candidate = context.work / "source.wav"
    return candidate if candidate.is_file() else None


def _overlap_samples(
    spans: list[tuple[int, int]],
    cuts: list[tuple[int, int]],
) -> int:
    total = 0
    for start, end in spans:
        for cut_start, cut_end in cuts:
            low = max(start, cut_start)
            high = min(end, cut_end)
            if high > low:
                total += high - low
    return total


@contextlib.contextmanager
def _pcm_rms(path: Path | None) -> Iterator[Callable[[int, int], int] | None]:
    if path is None:
        yield None
        return
    try:
        opened = wave.open(str(path), "rb")  # noqa: SIM115 - closed below
    except (OSError, EOFError, wave.Error):
        yield None
        return
    with contextlib.closing(opened) as handle:
        channels = max(1, handle.getnchannels())
        width = handle.getsampwidth()

        def rms(start: int, end: int) -> int:
            start = max(0, start)
            end = max(start + 1, end)
            try:
                handle.setpos(start)
                data = handle.readframes(end - start)
            except (OSError, wave.Error):
                return 0
            if not data:
                return 0
            if width != 2:
                return 0
            samples = array.array("h")
            samples.frombytes(data)
            if channels > 1:
                samples = samples[::channels]
            if not samples:
                return 0
            total = sum(sample * sample for sample in samples)
            return int(math.sqrt(total / len(samples)))

        yield rms


@register_step
class TimelineStep(BaseStep):
    type = "edit.timeline"
    version = "7"
    title = "Build timeline"
    description = (
        "Turn kept speech spans into frame-quantised video and sample-aligned audio segments."
    )
    requires = ("audio.vad",)
    produces = ("timeline", "inactive_spans")
    params_model = TimelineParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = TimelineParams.model_validate(params)
        media = require_media(context)
        pad_before = (
            options.pad_before_ms
            if options.pad_before_ms is not None
            else int(context.metadata.get("speech_pad_before_ms", 120))
        )
        pad_after = (
            options.pad_after_ms
            if options.pad_after_ms is not None
            else int(context.metadata.get("speech_pad_after_ms", 150))
        )
        editorial_applied = bool(
            context.metadata.get("editorial_clean", {}).get("applied")
        )
        editorial_cuts = (
            [
                (int(start), int(end))
                for start, end in context.metadata.get("editorial_cuts", [])
                if int(end) > int(start)
            ]
            if editorial_applied
            else []
        )
        if editorial_applied:
            pad_before = max(
                int(pad_before),
                int(context.metadata.get("speech_pad_before_ms", 0) or 0),
            )
            pad_after = max(
                int(pad_after),
                int(context.metadata.get("speech_pad_after_ms", 0) or 0),
            )
        use_transcript = (
            options.use_transcript_spans
            and bool(context.metadata.get("transcript_normalized"))
            and bool(context.transcript)
        )
        kept_gaps: list[tuple[int, int]] = []
        repeat_cuts: list[tuple[int, int]] = []
        if options.detect_repeats and context.transcript:
            plan = plan_word_cuts(
                context.transcript,
                set(context.discard_sentence_ids),
                sample_rate=media.audio_sample_rate,
                max_gap_seconds=options.repeat_max_gap_seconds,
                min_words=max(4, options.repeat_min_words),
                max_cut_ratio=options.word_cut_max_ratio,
                remove_fillers=options.remove_fillers,
                repeat_gap_seconds=options.repeat_gap_seconds,
            )
            repeat_cuts = plan.cuts
            if repeat_cuts:
                ratio = plan.cut_words / max(1, plan.total_words)
                context.warnings.append(
                    f"Removed {len(repeat_cuts)} word-level repeat(s) "
                    f"({plan.cut_words} words, {ratio:.1%})."
                )
                context.metadata["word_cuts"] = plan.to_dict()
                context.metadata["repeat_cuts"] = plan.report
        if use_transcript:
            with _pcm_rms(_pcm_path(context)) as rms_at:
                speech, noise_spans = transcript_spans(
                    context.transcript,
                    set(context.discard_sentence_ids),
                    sample_rate=media.audio_sample_rate,
                    duration_samples=context.duration_samples(),
                    pad_before_ms=pad_before,
                    pad_after_ms=pad_after,
                    head_guard_ms=options.head_guard_ms,
                    tail_guard_ms=options.tail_guard_ms,
                    guard_energy_threshold=options.guard_energy_threshold,
                    noise_mode=options.noise_filter,
                    noise_confidence=options.noise_confidence,
                    max_internal_gap_ms=options.max_internal_gap_ms,
                    internal_gap_mode=options.internal_gap_mode,
                    gap_energy_threshold=options.gap_energy_threshold,
                    long_gap_ms=options.long_gap_ms,
                    drop_isolated_words=options.drop_isolated_words,
                    rms_at=rms_at,
                    kept_gaps=kept_gaps,
                    forced_cuts=[
                        *context.retake_overlap_cuts,
                        *repeat_cuts,
                        *editorial_cuts,
                    ],
                )
                if options.keep_untranscribed:
                    before_seconds = sum(
                        end - start for start, end in speech
                    ) / media.audio_sample_rate
                    speech = add_untranscribed_spans(
                        speech,
                        context.speech_intervals,
                        context.transcript,
                        set(context.discard_sentence_ids),
                        sample_rate=media.audio_sample_rate,
                        duration_samples=context.duration_samples(),
                        min_ms=options.untranscribed_min_ms,
                        energy_threshold=options.untranscribed_energy_threshold,
                        pad_before_ms=pad_before,
                        pad_after_ms=pad_after,
                        rms_at=rms_at,
                        forced_cuts=[
                            *context.retake_overlap_cuts,
                            *repeat_cuts,
                            *editorial_cuts,
                        ],
                    )
                    after_seconds = sum(
                        end - start for start, end in speech
                    ) / media.audio_sample_rate
                    if after_seconds > before_seconds:
                        context.warnings.append(
                            "Kept "
                            f"{after_seconds - before_seconds:.1f}s of long "
                            "speech-like audio without transcript words."
                        )
                        context.metadata["untranscribed_added"] = {
                            "seconds": round(after_seconds - before_seconds, 3),
                            "min_ms": options.untranscribed_min_ms,
                        }
                    noise_spans = [
                        span
                        for span in noise_spans
                        if not any(
                            span.start_sample < end and span.end_sample > start
                            for start, end in speech
                        )
                    ]
                if options.remove_impulsive_noise:
                    pcm = load_pcm_mono(
                        _pcm_path(context),
                        sample_rate=media.audio_sample_rate,
                    )
                    kept_words = [
                        (word.start_sample, word.end_sample)
                        for sentence in context.transcript
                        if sentence.id not in set(context.discard_sentence_ids)
                        for word in sentence.words
                    ]
                    event_model = load_model() if options.use_audio_event_model else None
                    impulsive = detect_audio_events(
                        pcm,
                        kept_words,
                        sample_rate=media.audio_sample_rate,
                        model=event_model,
                        min_ms=options.impulsive_noise_min_ms,
                        max_ms=options.impulsive_noise_max_ms,
                        margin_ms=options.impulsive_noise_margin_ms,
                        use_ast=options.use_ast_audio_tagger,
                        ast_threshold=options.ast_noise_threshold,
                    )
                    if impulsive:
                        speech = subtract_spans(speech, impulsive)
                        noise_spans.extend(
                            InactiveSpan(
                                start_sample=start,
                                end_sample=end,
                                reason="noise",
                            )
                            for start, end in impulsive
                        )
                        seconds = sum(
                            end - start for start, end in impulsive
                        ) / media.audio_sample_rate
                        context.warnings.append(
                            f"Removed {len(impulsive)} impulsive non-speech event(s) "
                            f"({seconds:.1f}s)."
                        )
                        context.metadata["impulsive_noise"] = {
                            "spans": len(impulsive),
                            "seconds": round(seconds, 3),
                            "model": bool(event_model),
                        }
            context.metadata["timeline_units"] = "transcript"
            if kept_gaps:
                seconds = sum(
                    end - start for start, end in kept_gaps
                ) / media.audio_sample_rate
                context.warnings.append(
                    f"Kept {len(kept_gaps)} long speech-like gap(s) "
                    f"({seconds:.1f}s) as possible untranscribed speech."
                )
                context.metadata["kept_internal_gaps"] = {
                    "spans": len(kept_gaps),
                    "seconds": round(seconds, 3),
                }
        else:
            noise_spans = detect_noise_spans(
                context.speech_intervals,
                context.transcript,
                sample_rate=media.audio_sample_rate,
                mode=options.noise_filter,
                min_ms=options.noise_min_ms,
                confidence=options.noise_confidence,
            )
            raw_speech = context.speech_intervals
            removals: list[tuple[int, int]] = []
            if noise_spans:
                removals.extend(
                    (span.start_sample, span.end_sample) for span in noise_spans
                )
            discard_ids = set(context.discard_sentence_ids)
            removals.extend(
                (sentence.start_sample, sentence.end_sample)
                for sentence in context.transcript
                if sentence.id in discard_ids
            )
            removals.extend(
                (span.start_sample, span.end_sample)
                for span in context.retake_spans
            )
            removals.extend(context.retake_overlap_cuts)
            removals.extend(repeat_cuts)
            removals.extend(editorial_cuts)
            if removals:
                raw_speech = subtract_spans(raw_speech, removals)
            speech = pad_spans(
                raw_speech,
                media.audio_sample_rate,
                pad_before,
                pad_after,
                context.duration_samples(),
            )
            context.metadata["timeline_units"] = "vad"
        deliberate_cuts = [
            *context.retake_overlap_cuts,
            *repeat_cuts,
            *editorial_cuts,
        ]
        removed_spans = [
            *deliberate_cuts,
            *((span.start_sample, span.end_sample) for span in noise_spans),
        ]
        pcm_path = _pcm_path(context)
        silences = detect_silence_spans(
            pcm_path,
            sample_rate=media.audio_sample_rate,
            frame_ms=options.silence_frame_ms,
            threshold_db=options.silence_threshold_db,
            min_ms=100,
        )
        if not silences:
            silences = list(context.silence_spans)
        speech, capped_seconds = cap_silence_spans(
            speech,
            silences,
            sample_rate=media.audio_sample_rate,
            max_silence_ms=options.max_silence_ms,
            keep_silence_ms=options.keep_silence_ms,
            pad_before_ms=pad_before,
            pad_after_ms=pad_after,
            min_clip_ms=options.min_clip_ms,
        )
        if options.repair_word_tails:
            speech = repair_clipped_words(
                speech,
                context.transcript,
                set(context.discard_sentence_ids),
                sample_rate=media.audio_sample_rate,
                max_word_ms=options.word_repair_max_ms,
                guard_ms=options.silence_word_margin_ms,
            )
        if removed_spans:
            speech = exclude_removed_audio(
                speech,
                removed_spans,
                context.transcript,
                set(context.discard_sentence_ids),
                duration_samples=context.duration_samples(),
                minimum=max(1, round(media.audio_sample_rate * 0.02)),
            )
        if capped_seconds:
            context.warnings.append(
                f"Silence cap removed {capped_seconds:.1f}s "
                f"(max {options.max_silence_ms} ms)."
            )
            context.metadata["silence_cap"] = {
                "removed_seconds": round(capped_seconds, 3),
                "max_silence_ms": options.max_silence_ms,
                "keep_silence_ms": options.keep_silence_ms,
            }
        if noise_spans:
            seconds = sum(
                span.end_sample - span.start_sample for span in noise_spans
            ) / media.audio_sample_rate
            context.warnings.append(
                f"Noise filter removed {len(noise_spans)} non-speech span(s) "
                f"({seconds:.1f}s)."
            )
            context.metadata["noise_filter"] = {
                "mode": options.noise_filter,
                "spans": len(noise_spans),
                "seconds": round(seconds, 3),
                "units": context.metadata.get("timeline_units", "vad"),
            }
        speech, integrity_violations = enforce_word_integrity(
            speech,
            context.transcript,
            set(context.discard_sentence_ids),
            removed_spans=removed_spans,
            sample_rate=media.audio_sample_rate,
            max_word_ms=options.word_integrity_max_ms,
            max_gap_ms=options.word_integrity_gap_ms,
        )
        context.metadata["word_integrity"] = {
            "violations": len(integrity_violations),
            "max_word_ms": options.word_integrity_max_ms,
            "max_gap_ms": options.word_integrity_gap_ms,
        }
        if integrity_violations:
            context.warnings.append(
                f"{len(integrity_violations)} kept word(s) could not be kept whole."
            )
        leaked = _overlap_samples(speech, deliberate_cuts) / media.audio_sample_rate
        context.metadata["cut_leak"] = {
            "seconds": round(leaked, 3),
            "cuts": len(deliberate_cuts),
            "source": "timeline",
        }
        if deliberate_cuts and leaked > 0.05:
            context.warnings.append(
                f"{leaked:.2f}s of removed speech leaked back into the "
                "timeline; check word-integrity merges and padding."
            )
        editorial_crossfade = (
            context.metadata.get("editorial_crossfade_ms")
            if editorial_applied
            else None
        )
        audio_crossfade_ms = (
            int(editorial_crossfade)
            if editorial_crossfade is not None
            else options.audio_crossfade_ms
        )
        jl = JlCutsConfig(
            enable_j_cuts=options.enable_j_cuts,
            enable_l_cuts=options.enable_l_cuts,
            offset_ms=options.offset_ms,
            audio_crossfade_ms=audio_crossfade_ms,
            fade_in_ms=options.fade_in_ms,
            fade_out_ms=options.fade_out_ms,
            fade_curve=options.fade_curve,
            handle_check=options.handle_check,
        )
        zooms = ZoomsConfig(
            mode=options.zoom_mode,
            min_scale=options.zoom_min_scale,
            max_scale=options.zoom_max_scale,
            punch_in_scale=options.punch_in_scale,
            anchor_point=options.anchor_point,
            progressive_zoom=options.progressive_zoom,
            pan_direction=options.pan_direction,
        )
        io.report(20, "Building the cut timeline")
        built = build_timeline(
            media,
            speech,
            jl=jl,
            zooms=zooms,
            transition_frames=options.transition_frames,
            transition_type=options.transition_type,
            final_tail_guard_ms=options.final_tail_guard_ms,
        )
        inactive = build_inactive_segments(
            media,
            built.video_segments,
            silence_spans=context.silence_spans,
            retake_spans=context.retake_spans,
            noise_spans=noise_spans,
        )
        revision = options.revision
        if options.replace_manual:
            existing = context.output / "project_state.json"
            if existing.is_file():
                try:
                    current = ProjectState.model_validate_json(
                        existing.read_text(encoding="utf-8")
                    )
                except (OSError, ValueError):
                    current = None
                if current is not None and current.revision > revision:
                    revision = current.revision + 1
                    context.warnings.append(
                        "Manual timeline edits at revision "
                        f"{current.revision} were replaced by this recipe build."
                    )
        from videoflow.application.projects import project_uuid

        project_id = project_uuid(options.project_id) if options.project_id else uuid4()
        context.state = ProjectState(
            project_id=project_id,
            revision=revision,
            media_info=media,
            vad_intervals=[
                SampleSpan(start_sample=start, end_sample=end) for start, end in speech
            ],
            transcript=list(context.transcript),
            retake_culls=list(context.discard_sentence_ids),
            retake_guard_restores=list(context.restored_sentence_ids),
            manual_overrides=list(context.manual_overrides),
            video_segments=list(built.video_segments),
            audio_segments=list(built.audio_segments),
            inactive_segments=list(inactive),
        )
        context.inactive_spans = [
            InactiveSpan(
                start_sample=segment.audio.source_in_sample,
                end_sample=segment.audio.source_out_sample,
                reason=segment.reason,
            )
            for segment in inactive
        ]
        context.speech_intervals = speech
        context.warnings.extend(built.warnings)
        context.hashes["timeline"] = digest_payload(
            {
                "spans": speech,
                "video": len(built.video_segments),
                "audio": len(built.audio_segments),
                "inactive": len(inactive),
                "noise": [span.model_dump() for span in noise_spans],
                "silence": {
                    "max_ms": options.max_silence_ms,
                    "keep_ms": options.keep_silence_ms,
                },
                "jl": jl.model_dump(),
                "zooms": zooms.model_dump(),
            }
        )
        io.report(100, f"{len(built.video_segments)} cuts ready")
