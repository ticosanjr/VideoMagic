"""Optional forced alignment for imported or sparse transcripts.

WhisperX is the preferred backend. When it is not installed, a faster-whisper
ASR pass provides word timings without replacing the original text.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.faster_whisper import FasterWhisperAdapter
from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.core.context import PipelineContext
from videoflow.domain.state import Sentence, WordTiming
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step

Backend = Literal["auto", "whisperx", "faster_whisper", "none"]


class ForcedAlignmentParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Backend = "auto"
    model_size: Literal["tiny", "base", "small", "medium", "large-v2", "large-v3"] = "small"
    language: str = "auto"
    device: Literal["cpu", "cuda", "auto"] = "cpu"
    compute_type: str = "int8"
    min_words: int = Field(default=1, ge=0, le=100)


def _device(value: str) -> str:
    return "cuda" if value == "cuda" else "cpu"


def _whisperx_words(
    source: Path, options: ForcedAlignmentParams, sample_rate: int
) -> tuple[list[tuple[str, int, int]], str, float]:
    import whisperx  # type: ignore[import-not-found]

    audio = whisperx.load_audio(str(source))
    device = _device(options.device)
    model = whisperx.load_model(
        options.model_size,
        device,
        compute_type=options.compute_type,
    )
    language = None if options.language == "auto" else options.language
    result = model.transcribe(audio, language=language)
    detected = str(result.get("language") or language or "en")
    align_model, metadata = whisperx.load_align_model(language_code=detected, device=device)
    aligned = whisperx.align(
        result["segments"],
        align_model,
        metadata,
        audio,
        device,
        return_char_alignments=False,
    )
    probability = float(result.get("language_probability") or 0.0)
    words: list[tuple[str, int, int]] = []
    for segment in aligned.get("segments", []):
        for item in segment.get("words", []):
            if not isinstance(item, dict) or not item.get("word"):
                continue
            start = int(round(float(item.get("start") or 0.0) * sample_rate))
            end = int(round(float(item.get("end") or 0.0) * sample_rate))
            if end > start:
                words.append((str(item["word"]).strip(), start, end))
    return words, detected, probability


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
    source: Path, options: ForcedAlignmentParams, sample_rate: int, io: StepIO
) -> tuple[list[tuple[str, int, int]], str, str, float]:
    if options.backend in {"auto", "whisperx"}:
        try:
            io.report(20, "Aligning words with WhisperX")
            words, language, probability = _whisperx_words(source, options, sample_rate)
            if words:
                return words, "whisperx", language, probability
        except Exception as exc:  # noqa: BLE001 - optional dependency or model
            if options.backend == "whisperx":
                io.emit("warning", f"WhisperX alignment failed: {exc}", module="align")
    if options.backend in {"auto", "faster_whisper", "whisperx"}:
        io.report(50, "Aligning words with faster-whisper")
        words, language, probability = _faster_whisper_words(source, options, sample_rate)
        if words:
            return words, "faster_whisper", language, probability
    return [], "none", "", 0.0


def _words_in_range(
    words: list[tuple[str, int, int]], start: int, end: int
) -> list[tuple[str, int, int]]:
    return [item for item in words if start <= (item[1] + item[2]) // 2 <= end]


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
        words, backend, language, probability = _align_words(source, options, rate, io)
        if not words:
            context.warnings.append(
                "Forced alignment skipped: WhisperX and faster-whisper are unavailable."
            )
            io.report(100, "Forced alignment unavailable")
            return
        aligned = 0
        updated: list[Sentence] = []
        for sentence in context.transcript:
            sentence_words = _words_in_range(words, sentence.start_sample, sentence.end_sample)
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
        context.metadata["forced_alignment"] = payload
        target = context.output / "alignment" / "forced.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        context.artifacts["forced_alignment"] = str(target)
        io.report(100, f"{aligned} sentence(s) aligned ({backend})")
