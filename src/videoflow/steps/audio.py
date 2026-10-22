"""Voice activity detection step."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.silero import SileroVadAdapter
from videoflow.application.vad import detect_speech
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.cache import cache_get, cache_key, cache_put
from videoflow.steps.common import adapter_for, digest_payload, require_media
from videoflow.steps.registry import register_step


class VadParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: Literal["auto", "silero", "ffmpeg"] = "auto"
    noise_db: float = -30.0
    min_silence_ms: int = Field(default=400, ge=0)
    min_speech_ms: int = Field(default=100, ge=0)
    speech_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    pad_before_ms: int = Field(default=120, ge=0)
    pad_after_ms: int = Field(default=150, ge=0)
    apply_pads: bool = False


@register_step
class VadStep(BaseStep):
    type = "audio.vad"
    title = "Voice detection"
    description = "Detect speech and silence with Silero VAD or the FFmpeg fallback."
    requires = ("ingest",)
    produces = ("speech_intervals",)
    params_model = VadParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = VadParams.model_validate(params)
        media = require_media(context)
        adapter = adapter_for(context, io)
        key = cache_key(
            {
                "kind": "vad",
                "source": context.pcm_digest or str(context.source),
                "params": options.model_dump(mode="json"),
                "silero": SileroVadAdapter.available(),
            }
        )
        cached = cache_get("vad", key)
        if cached is not None:
            spans = [(int(start), int(end)) for start, end in cached.get("spans", [])]
            if spans:
                context.speech_intervals = spans
                context.vad_engine = str(cached.get("engine", "cache"))
                context.metadata["speech_pad_before_ms"] = options.pad_before_ms
                context.metadata["speech_pad_after_ms"] = options.pad_after_ms
                context.metadata["min_speech_ms"] = options.min_speech_ms
                context.hashes["vad"] = key
                context.cache_hits.append("audio.vad")
                io.emit("info", f"{len(spans)} speech intervals (cached)")
                io.report(100, "Speech intervals loaded from cache")
                return
        context.cache_misses.append("audio.vad")
        io.report(15, "Detecting speech and silence")
        detection = detect_speech(
            adapter,
            Path(context.source),
            context.work,
            media,
            vad_engine=options.engine,
            noise_db=options.noise_db,
            min_silence_ms=options.min_silence_ms,
            min_speech_ms=options.min_speech_ms,
            speech_threshold=options.speech_threshold,
            speech_pad_before_ms=options.pad_before_ms,
            speech_pad_after_ms=options.pad_after_ms,
            duration_samples=context.duration_samples(),
            apply_pads=options.apply_pads,
            log=lambda level, message: io.emit(level, message, module="vad"),
        )
        if not detection.spans:
            raise IngestError(
                "No speech detected. Lower the noise threshold or the minimum silence duration."
            )
        context.speech_intervals = list(detection.spans)
        context.vad_engine = detection.engine
        context.metadata["speech_pad_before_ms"] = options.pad_before_ms
        context.metadata["speech_pad_after_ms"] = options.pad_after_ms
        context.metadata["min_speech_ms"] = options.min_speech_ms
        context.hashes["vad"] = digest_payload(
            {"spans": detection.spans, "engine": detection.engine}
        )
        cache_put(
            "vad",
            key,
            {"spans": detection.spans, "engine": detection.engine},
        )
        io.emit("info", f"{len(detection.spans)} speech intervals ({detection.engine})")
        io.report(100, "Speech intervals ready")
