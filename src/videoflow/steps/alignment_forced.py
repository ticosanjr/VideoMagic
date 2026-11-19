"""Optional forced alignment for imported or sparse transcripts.

WhisperX is the preferred backend. When it is not installed, a faster-whisper
ASR pass provides word timings without replacing the original text.
"""

from __future__ import annotations

import json
from bisect import bisect_left, bisect_right
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.faster_whisper import FasterWhisperAdapter
from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.core.context import PipelineContext
from videoflow.domain.state import Sentence, WordTiming
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step

Backend = Literal["auto", "whisperx", "stable_ts", "faster_whisper", "none"]


class ForcedAlignmentParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Backend = "auto"
    model_size: Literal[
        "tiny", "base", "small", "medium", "large-v2", "large-v3", "large-v3-turbo"
    ] = "small"
    language: str = "auto"
    device: Literal["cpu", "cuda", "auto"] = "cpu"
    compute_type: str = "int8"
    compute_policy: Literal["auto", "local", "remote", "remote_only"] = "auto"
    min_words: int = Field(default=1, ge=0, le=100)


def _device(value: str) -> str:
    return "cuda" if value == "cuda" else "cpu"


def _words_from_payload(
    payload: dict[str, Any],
    sample_rate: int,
) -> list[tuple[str, int, int]]:
    words: list[tuple[str, int, int]] = []
    for segment in payload.get("segments", []) or []:
        if not isinstance(segment, dict):
            continue
        for item in segment.get("words", []) or []:
            if not isinstance(item, dict) or not item.get("word"):
                continue
            start = int(round(float(item.get("start") or 0.0) * sample_rate))
            end = int(round(float(item.get("end") or 0.0) * sample_rate))
            if end > start:
                words.append((str(item["word"]).strip(), start, end))
    if words:
        return words
    # Some stable-ts payloads expose words at the top level.
    for item in payload.get("words", []) or []:
        if not isinstance(item, dict) or not item.get("word"):
            continue
        start = int(round(float(item.get("start") or 0.0) * sample_rate))
        end = int(round(float(item.get("end") or 0.0) * sample_rate))
        if end > start:
            words.append((str(item["word"]).strip(), start, end))
    return words


def _whisperx_words(
    source: Path,
    options: ForcedAlignmentParams,
    sample_rate: int,
    sentences: list[Sentence] | None = None,
) -> tuple[list[tuple[str, int, int]], str, float]:
    import whisperx  # type: ignore[import-not-found]

    audio = whisperx.load_audio(str(source))
    device = _device(options.device)
    language = None if options.language == "auto" else options.language
    if sentences:
        segments = [
            {
                "start": sentence.start_sample / sample_rate,
                "end": sentence.end_sample / sample_rate,
                "text": sentence.text,
            }
            for sentence in sentences
        ]
        detected = options.language if options.language != "auto" else "en"
        probability = 0.0
    else:
        model = whisperx.load_model(
            options.model_size,
            device,
            compute_type=options.compute_type,
        )
        result = model.transcribe(audio, language=language)
        segments = result["segments"]
        detected = str(result.get("language") or language or "en")
        probability = float(result.get("language_probability") or 0.0)
    align_model, metadata = whisperx.load_align_model(language_code=detected, device=device)
    aligned = whisperx.align(
        segments,
        align_model,
        metadata,
        audio,
        device,
        return_char_alignments=False,
    )
    return _words_from_payload(aligned, sample_rate), detected, probability


def _stable_ts_words(
    source: Path,
    options: ForcedAlignmentParams,
    sample_rate: int,
    sentences: list[Sentence] | None = None,
) -> tuple[list[tuple[str, int, int]], str, float]:
    import stable_whisper  # type: ignore[import-not-found]

    model = stable_whisper.load_model(options.model_size)
    language = None if options.language == "auto" else options.language
    payload: dict[str, Any]
    if sentences:
        text = " ".join(sentence.text for sentence in sentences if sentence.text.strip())
        result = model.align(str(source), text, language=language)
    else:
        result = model.transcribe(str(source), language=language, word_timestamps=True)
    payload = result.to_dict() if hasattr(result, "to_dict") else result
    return _words_from_payload(payload, sample_rate), options.language, 0.0


def _faster_whisper_words(
    source: Path, options: ForcedAlignmentParams, sample_rate: int
) -> tuple[list[tuple[str, int, int]], str, float]:
    if not FasterWhisperAdapter.available(options.model_size):  # type: ignore[arg-type]
        return [], "", 0.0
    adapter = FasterWhisperAdapter(
        model_size=options.model_size,
        device=options.device,
        compute_type=options.compute_type,
        language=options.language,
        vad_filter=False,
    )
    asr = adapter.transcribe(source, sample_rate)
    words = [
        (word.word, word.start_sample, word.end_sample)
        for sentence in asr
        for word in sentence.words
    ]
    return (
        words,
        str(getattr(adapter, "last_language", "") or ""),
        float(getattr(adapter, "last_language_probability", 0.0) or 0.0),
    )


def _align_words(
    source: Path,
    options: ForcedAlignmentParams,
    sample_rate: int,
    io: StepIO,
    sentences: list[Sentence] | None = None,
) -> tuple[list[tuple[str, int, int]], str, str, float]:
    if options.backend in {"auto", "whisperx"}:
        try:
            io.report(20, "Aligning words with WhisperX")
            words, language, probability = _whisperx_words(
                source, options, sample_rate, sentences
            )
            if words:
                return words, "whisperx", language, probability
        except Exception as exc:  # noqa: BLE001 - optional dependency or model
            if options.backend == "whisperx":
                io.emit("warning", f"WhisperX alignment failed: {exc}", module="align")
    if options.backend in {"auto", "stable_ts"}:
        try:
            io.report(35, "Aligning words with stable-ts")
            words, language, probability = _stable_ts_words(
                source, options, sample_rate, sentences
            )
            if words:
                return words, "stable_ts", language, probability
        except Exception as exc:  # noqa: BLE001 - optional dependency or model
            if options.backend == "stable_ts":
                io.emit("warning", f"stable-ts alignment failed: {exc}", module="align")
    if options.backend in {"auto", "faster_whisper", "whisperx", "stable_ts"}:
        io.report(50, "Aligning words with faster-whisper")
        words, language, probability = _faster_whisper_words(source, options, sample_rate)
        if words:
            return words, "faster_whisper", language, probability
    return [], "none", "", 0.0


def _remote_words(
    source: Path,
    options: ForcedAlignmentParams,
    sample_rate: int,
    io: StepIO,
) -> tuple[list[tuple[str, int, int]], str, float, dict[str, Any]]:
    from videoflow.application.asr_remote import RemoteAsrClient
    from videoflow.application.compute import router_from_settings

    router = router_from_settings()
    decision = router.decide("asr")
    if not decision.is_remote:
        if options.compute_policy == "remote_only":
            raise RuntimeError(f"remote alignment requested but unavailable: {decision.reason}")
        return [], "", 0.0, {}
    io.report(65, "Aligning words with the remote worker")
    client = RemoteAsrClient(
        router,
        language=options.language,
        model=options.model_size,
        beam_size=1,
        word_timestamps=True,
        vad_filter=False,
        capability="forced_align",
    )
    try:
        sentences = client.transcribe(source, sample_rate)
    except Exception:
        client = RemoteAsrClient(
            router,
            language=options.language,
            model=options.model_size,
            beam_size=1,
            word_timestamps=True,
            vad_filter=False,
            capability="asr",
        )
        sentences = client.transcribe(source, sample_rate)
    words = [
        (word.word, word.start_sample, word.end_sample)
        for sentence in sentences
        for word in sentence.words
    ]
    return (
        words,
        str(client.last_language or ""),
        float(client.last_language_probability or 0.0),
        dict(client.execution),
    )


def _words_in_range(
    words: list[tuple[str, int, int]], start: int, end: int
) -> list[tuple[str, int, int]]:
    return [item for item in words if start <= (item[1] + item[2]) // 2 <= end]


def _word_ranges(
    words: list[tuple[str, int, int]], sentences: list[Sentence]
) -> list[tuple[int, int]] | None:
    """Return contiguous word slices when both sequences are time ordered."""

    if not words or not sentences:
        return [(0, 0) for _ in sentences]
    midpoints = [(start + end) // 2 for _word, start, end in words]
    if any(left > right for left, right in zip(midpoints, midpoints[1:], strict=False)):
        return None
    return [
        (
            bisect_left(midpoints, sentence.start_sample),
            bisect_right(midpoints, sentence.end_sample),
        )
        for sentence in sentences
    ]


@register_step
class ForcedAlignmentStep(BaseStep):
    type = "alignment.forced"
    title = "Forced alignment"
    description = (
        "Add word-level timings to an existing transcript with WhisperX, "
        "falling back to faster-whisper, without replacing its text."
    )
    status = "partial"
    icon = "↔"
    color = "#38bdf8"
    requires = ("transcribe",)
    produces = ("transcript", "forced_alignment")
    params_model = ForcedAlignmentParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ForcedAlignmentParams.model_validate(params)
        if options.language == "auto":
            preferred = context.transcript_language or (
                context.state.language if context.state is not None else ""
            )
            if preferred:
                options = options.model_copy(update={"language": preferred})
        if not context.transcript:
            io.report(100, "No transcript; alignment skipped")
            return
        if options.backend == "none":
            io.report(100, "Forced alignment disabled")
            return
        source = Path(context.pcm_path or context.source)
        if source.suffix.casefold() != ".wav":
            wav = context.work / "alignment.wav"
            FFmpegAdapter().extract_pcm(source, wav, sample_rate=16000)
            source = wav
        rate = context.media.audio_sample_rate if context.media is not None else 48000
        execution: dict[str, Any] = {}
        words: list[tuple[str, int, int]] = []
        backend = "none"
        language = ""
        probability = 0.0
        if options.compute_policy in {"remote", "remote_only"}:
            try:
                words, language, probability, execution = _remote_words(
                    source, options, rate, io
                )
                if words:
                    backend = "remote_asr"
            except Exception as exc:  # noqa: BLE001 - policy may require remote
                if options.compute_policy == "remote_only":
                    raise
                context.warnings.append(f"Remote alignment unavailable: {exc}")
        if not words:
            words, backend, language, probability = _align_words(
                source, options, rate, io, context.transcript
            )
        if not words and options.compute_policy == "auto":
            try:
                words, language, probability, execution = _remote_words(
                    source, options, rate, io
                )
                if words:
                    backend = "remote_asr"
            except Exception as exc:  # noqa: BLE001 - optional remote fallback
                context.warnings.append(f"Remote alignment unavailable: {exc}")
        if not words:
            context.warnings.append(
                "Forced alignment skipped: WhisperX, stable-ts, faster-whisper, "
                "and the remote ASR worker are unavailable."
            )
            io.report(100, "Forced alignment unavailable")
            return
        aligned = 0
        updated: list[Sentence] = []
        ranges = _word_ranges(words, context.transcript)
        for position, sentence in enumerate(context.transcript):
            if ranges is None:
                sentence_words = _words_in_range(words, sentence.start_sample, sentence.end_sample)
            else:
                start_index, end_index = ranges[position]
                sentence_words = words[start_index:end_index]
            if len(sentence_words) < options.min_words:
                updated.append(sentence)
                continue
            updated.append(
                sentence.model_copy(
                    update={
                        "start_sample": min(item[1] for item in sentence_words),
                        "end_sample": max(item[2] for item in sentence_words),
                        "words": [
                            WordTiming(
                                word=item[0],
                                start_sample=item[1],
                                end_sample=item[2],
                                probability=1.0,
                            )
                            for item in sentence_words
                        ],
                    }
                )
            )
            aligned += 1
        context.transcript = updated
        detected = language or options.language
        if detected == "auto":
            detected = ""
        if detected:
            context.transcript_language = detected
            context.language_confidence = max(0.0, min(1.0, probability))
            if context.state is not None:
                context.state = context.state.model_copy(
                    update={
                        "language": detected,
                        "language_confidence": context.language_confidence,
                    }
                )
        payload: dict[str, Any] = {
            "backend": backend,
            "model_size": options.model_size,
            "language": detected,
            "language_probability": round(max(0.0, min(1.0, probability)), 4),
            "sentences": len(updated),
            "aligned": aligned,
            "words": len(words),
        }
        if execution:
            payload["execution"] = execution
        context.metadata["forced_alignment"] = payload
        target = context.output / "alignment" / "forced.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        context.artifacts["forced_alignment"] = str(target)
        io.report(100, f"{aligned} sentence(s) aligned ({backend})")
