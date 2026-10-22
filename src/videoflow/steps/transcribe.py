"""Transcription step with local, HTTP, SRT, and project-transcript modes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from videoflow.adapters.asr import WhisperHttpAdapter
from videoflow.adapters.faster_whisper import FasterWhisperAdapter
from videoflow.adapters.whisper import WhisperCliAdapter
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError, TranscriptionError
from videoflow.domain.transcript import parse_srt_file
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import adapter_for, digest_payload, require_media
from videoflow.steps.registry import register_step

Mode = Literal[
    "auto",
    "none",
    "srt",
    "project",
    "faster_whisper",
    "whisper_cpp",
    "http",
]


class TranscribeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Mode = "auto"
    srt_path: str | None = None
    model_size: Literal["tiny", "base", "small", "medium", "large-v2", "large-v3"] = "small"
    language: str = "pt"
    device: Literal["cpu", "cuda", "auto"] = "cpu"
    compute_type: str = "int8"
    vad_filter: bool = False
    base_url: str | None = None
    model: str = "whisper-1"
    api_key_env: str = "VIDEOWFLOW_ASR_API_KEY"
    whisper_binary: str | None = None
    whisper_model: str | None = None


@register_step
class TranscribeStep(BaseStep):
    type = "transcribe"
    title = "Transcribe"
    description = "Read an SRT, reuse a project transcript, or call local/HTTP speech-to-text."
    requires = ("ingest",)
    produces = ("transcript",)
    params_model = TranscribeParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = TranscribeParams.model_validate(params)
        media = require_media(context)
        mode = options.mode
        if mode == "auto":
            if options.srt_path:
                mode = "srt"
            elif context.transcript:
                mode = "project"
            else:
                mode = self._available_mode(context, io)
        if mode == "none":
            context.transcript = []
            context.transcript_source = "none"
            io.report(100, "Transcription skipped")
            return
        if mode == "project":
            if not context.transcript:
                raise IngestError("No project transcript is available for this run")
            context.transcript_source = "project"
            io.report(100, f"{len(context.transcript)} sentences from project state")
            return
        if mode == "srt":
            path = Path(options.srt_path or "").expanduser()
            if not path.is_file():
                raise IngestError(f"Subtitle file does not exist: {path}")
            io.report(25, "Reading subtitle transcript")
            context.transcript = parse_srt_file(path, media.audio_sample_rate)
            context.transcript_source = "srt"
            if not context.transcript:
                raise TranscriptionError("The subtitle file contains no usable sentences")
            context.hashes["transcribe"] = digest_payload(
                [sentence.model_dump(mode="json") for sentence in context.transcript]
            )
            io.report(100, f"{len(context.transcript)} sentences from SRT")
            return

        io.report(20, "Preparing speech-to-text")
        client = io.asr_client
        if client is None:
            if mode == "http":
                base_url = options.base_url or os.environ.get("VIDEOWFLOW_ASR_BASE_URL")
                if not base_url:
                    raise TranscriptionError("HTTP transcription requires base_url")
                client = WhisperHttpAdapter(
                    base_url=base_url,
                    model=options.model,
                    api_key=os.environ.get(options.api_key_env),
                    language=options.language,
                )
            elif mode == "whisper_cpp":
                client = WhisperCliAdapter(
                    binary=options.whisper_binary or os.environ.get("VIDEOWFLOW_WHISPER_BIN"),
                    model=options.whisper_model or os.environ.get("VIDEOWFLOW_WHISPER_MODEL"),
                    language=options.language,
                    log=lambda level, message: io.emit(level, message, module="transcribe"),
                )
            else:
                client = FasterWhisperAdapter(
                    model_size=options.model_size,
                    device=options.device,
                    compute_type=options.compute_type,
                    language=options.language,
                    vad_filter=options.vad_filter,
                    log=lambda level, message: io.emit(level, message, module="transcribe"),
                )
        io.report(45, "Calling speech-to-text")
        adapter = adapter_for(context, io)
        wav = adapter.extract_pcm(
            Path(context.source), context.work / "transcribe.wav", sample_rate=16000
        )
        transcript = client.transcribe(wav, media.audio_sample_rate)
        if not transcript:
            raise TranscriptionError("Speech-to-text returned no sentences")
        context.transcript = list(transcript)
        context.transcript_source = mode
        context.hashes["transcribe"] = digest_payload(
            [sentence.model_dump(mode="json") for sentence in transcript]
        )
        io.emit("info", f"{len(transcript)} sentences from {mode}")
        io.report(100, "Transcript ready")

    @staticmethod
    def _available_mode(context: PipelineContext, io: StepIO) -> Mode:
        if FasterWhisperAdapter.available("small"):
            return "faster_whisper"
        if os.environ.get("VIDEOWFLOW_WHISPER_BIN") or os.environ.get(
            "VIDEOWFLOW_WHISPER_MODEL"
        ):
            return "whisper_cpp"
        if os.environ.get("VIDEOWFLOW_ASR_BASE_URL"):
            return "http"
        io.emit(
            "warning",
            "No speech-to-text engine is available; continuing without a transcript",
            module="transcribe",
        )
        context.warnings.append(
            "Transcription skipped: no local Whisper model or ASR endpoint configured"
        )
        return "none"
