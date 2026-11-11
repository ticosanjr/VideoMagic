"""ASR-assisted word timing for imported or sparse transcripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.faster_whisper import FasterWhisperAdapter
from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.core.context import PipelineContext
from videoflow.domain.state import Sentence, WordTiming
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class ForcedAlignmentParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Literal["auto", "faster_whisper", "none"] = "auto"
    model_size: Literal["tiny", "base", "small", "medium", "large-v2", "large-v3"] = (
        "small"
    )
    language: str = "auto"
    device: Literal["cpu", "cuda", "auto"] = "cpu"
    compute_type: str = "int8"
    min_words: int = Field(default=1, ge=0, le=100)


def _words_in_range(
    asr: list[Sentence], start: int, end: int
) -> list[tuple[str, int, int]]:
    words: list[tuple[str, int, int]] = []
    for sentence in asr:
        for word in sentence.words:
            midpoint = (word.start_sample + word.end_sample) // 2
            if start <= midpoint <= end:
                words.append((word.word, word.start_sample, word.end_sample))
    return words


@register_step
class ForcedAlignmentStep(BaseStep):
    type = "alignment.forced"
    title = "Forced alignment"
    description = (
        "Use a local ASR pass to add word-level timings to an existing "
        "transcript without replacing its text."
    )
    status = "partial"
    icon = "↔"
    color = "#38bdf8"
    requires = ("transcribe",)
    produces = ("transcript", "forced_alignment")
    params_model = ForcedAlignmentParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ForcedAlignmentParams.model_validate(params)
        if not context.transcript:
            io.report(100, "No transcript; alignment skipped")
            return
        if options.backend == "none" or not FasterWhisperAdapter.available(
            options.model_size  # type: ignore[arg-type]
        ):
            context.warnings.append(
                "Forced alignment skipped: faster-whisper is not available."
            )
            io.report(100, "Forced alignment unavailable")
            return
        source = Path(context.pcm_path or context.source)
        wav = context.work / "alignment.wav"
        if source.suffix.casefold() != ".wav":
            FFmpegAdapter().extract_pcm(source, wav, sample_rate=16000)
            source = wav
        client = FasterWhisperAdapter(
            model_size=options.model_size,
            device=options.device,
            compute_type=options.compute_type,
            language=options.language,
            vad_filter=False,
            log=lambda level, message: io.emit(level, message, module="align"),
        )
        rate = (
            context.media.audio_sample_rate if context.media is not None else 48000
        )
        asr = client.transcribe(source, rate)
        aligned = 0
        updated: list[Sentence] = []
        for sentence in context.transcript:
            words = _words_in_range(asr, sentence.start_sample, sentence.end_sample)
            if len(words) < options.min_words:
                updated.append(sentence)
                continue
            updated.append(
                sentence.model_copy(
                    update={
                        "start_sample": min(item[1] for item in words),
                        "end_sample": max(item[2] for item in words),
                        "words": [
                            WordTiming(
                                word=item[0],
                                start_sample=item[1],
                                end_sample=item[2],
                                probability=1.0,
                            )
                            for item in words
                        ],
                    }
                )
            )
            aligned += 1
        context.transcript = updated
        payload = {
            "backend": "faster_whisper",
            "model_size": options.model_size,
            "sentences": len(updated),
            "aligned": aligned,
            "asr_sentences": len(asr),
        }
        context.metadata["forced_alignment"] = payload
        target = context.output / "alignment" / "forced.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        context.artifacts["forced_alignment"] = str(target)
        io.report(100, f"{aligned} sentence(s) aligned")
