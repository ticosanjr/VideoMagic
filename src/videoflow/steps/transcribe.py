"""Transcription step with local, HTTP, SRT, and project-transcript modes."""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.asr import WhisperHttpAdapter
from videoflow.adapters.faster_whisper import FasterWhisperAdapter
from videoflow.adapters.whisper import WhisperCliAdapter
from videoflow.application.asr_profiles import resolve_asr_plan
from videoflow.application.secrets import get_secret
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError, TranscriptionError
from videoflow.domain.state import Sentence
from videoflow.domain.transcript import parse_srt_file
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.cache import cache_get, cache_key, cache_put
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

    provider_id: str = ""
    model_id: str = ""
    mode: Mode = "auto"
    srt_path: str | None = None
    model_size: Literal[
        "tiny", "base", "small", "medium", "large-v2", "large-v3", "large-v3-turbo"
    ] = "small"
    quality_profile: Literal[
        "auto", "custom", "fast", "balanced", "quality", "vulkan", "remote"
    ] = "auto"
    language: str = "pt"
    device: Literal["cpu", "cuda", "auto"] = "cpu"
    compute_type: str = "int8"
    beam_size: int = Field(default=0, ge=0, le=10)
    cpu_threads: int = Field(default=0, ge=0, le=128)
    word_timestamps: Literal["auto", "always", "off"] = "auto"
    condition_on_previous_text: bool | None = None
    vad_filter: bool | None = None
    base_url: str | None = None
    model: str = "whisper-1"
    api_key_env: str = "VIDEOWFLOW_ASR_API_KEY"
    whisper_binary: str | None = None
    whisper_model: str | None = None
    audio_source: Literal["source", "master", "isolated"] = "source"


def _supports_keyword(function: object, name: str) -> bool:
    """Whether a transcriber accepts an optional keyword argument."""

    try:
        parameters = inspect.signature(function).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD or parameter.name == name
        for parameter in parameters
    )


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
        try:
            from videoflow.application.settings import load_settings

            settings = load_settings()
        except Exception:
            settings = None
        if settings is not None and options.language == "pt":
            options = options.model_copy(
                update={"language": settings.speech.language}
            )
        if (
            settings is not None
            and not options.provider_id
            and options.mode == "auto"
            and not options.srt_path
            and not context.transcript
        ):
            plan = resolve_asr_plan(settings, options)
            if plan.fallback_reason:
                io.emit("warning", plan.fallback_reason, module="transcribe")
            options = options.model_copy(
                update={
                    "mode": plan.mode,
                    "model_id": plan.model_id or options.model_id,
                    "model_size": plan.model_size,
                    "device": plan.device,
                    "compute_type": plan.compute_type,
                    "beam_size": plan.beam_size,
                    "cpu_threads": plan.cpu_threads,
                    "vad_filter": plan.vad_filter,
                    "word_timestamps": "always"
                    if plan.word_timestamps
                    else "off",
                    "condition_on_previous_text": plan.condition_on_previous_text,
                    "base_url": plan.remote_base_url or options.base_url,
                    "model": plan.remote_model or options.model,
                    "api_key_env": plan.remote_api_key_env or options.api_key_env,
                }
            )
        model_id = options.model_id.strip()
        model_path: Path | None = None
        model_kind = ""
        if model_id:
            from videoflow.application.models import installed_path, list_models

            info = next(
                (item for item in list_models() if str(item.get("id")) == model_id),
                None,
            )
            if info is None:
                raise TranscriptionError(f"Unknown ASR model: {model_id}")
            if str(info.get("capability") or "") not in {"asr", "other"}:
                raise TranscriptionError(
                    f"Model {model_id} is not an ASR model"
                )
            model_path = installed_path(model_id)
            if model_path is None:
                raise TranscriptionError(
                    f"ASR model {model_id} is not installed. Download it in Setup → AI models."
                )
            model_kind = str(info.get("kind") or "")
        media = require_media(context)
        mode = options.mode
        if options.provider_id and mode not in {"srt", "project", "none"}:
            mode = "http"
        if model_kind and mode in {"auto", "faster_whisper", "whisper_cpp"}:
            if model_kind == "faster-whisper":
                mode = "faster_whisper"
            elif model_kind == "whisper":
                mode = "whisper_cpp"
            else:
                raise TranscriptionError(
                    f"ASR model {model_id} has unsupported kind {model_kind}"
                )
        if mode == "auto":
            if options.srt_path:
                mode = "srt"
            elif context.transcript:
                mode = "project"
            else:
                mode = self._available_mode(context, io)
        if mode == "faster_whisper" and media.duration_frames > 0:
            fps = media.fps_num / max(1, media.fps_den)
            audio_minutes = media.duration_frames / max(0.001, fps) / 60.0
            factors = {
                "tiny": 0.15,
                "base": 0.25,
                "small": 0.40,
                "medium": 0.80,
                "large-v2": 1.50,
                "large-v3": 1.60,
                "large-v3-turbo": 0.80,
            }
            factor = factors.get(options.model_size, 0.5)
            if options.device == "cuda":
                factor /= 6.0
            eta = audio_minutes * factor
            io.emit(
                "info",
                f"Transcription estimate: about {eta:.0f} min for "
                f"{audio_minutes:.1f} min of audio on {options.device} "
                f"({options.model_size}).",
                module="transcribe",
            )
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

        source_key = context.pcm_digest
        key = cache_key(
            {
                "kind": "transcript",
                "source": source_key,
                "mode": mode,
                "params": options.model_dump(mode="json"),
                "env_base_url": os.environ.get("VIDEOWFLOW_ASR_BASE_URL"),
                "client": type(io.asr_client).__name__ if io.asr_client is not None else "default",
            }
        ) if source_key else ""
        if key:
            cached = cache_get("transcript", key)
            if cached is not None:
                try:
                    context.transcript = [
                        Sentence.model_validate(item) for item in cached.get("sentences", [])
                    ]
                except (ValueError, TypeError):
                    context.transcript = []
                if context.transcript:
                    context.transcript_source = str(cached.get("source", mode))
                    context.hashes["transcribe"] = key
                    context.cache_hits.append("transcribe")
                    io.emit("info", f"{len(context.transcript)} sentences from cache")
                    io.report(100, "Transcript loaded from cache")
                    return
        context.cache_misses.append("transcribe")
        partial_path = context.work / "transcribe.partial.json"
        initial_sentences: list[Sentence] = []
        if source_key and partial_path.is_file():
            try:
                partial = json.loads(partial_path.read_text(encoding="utf-8"))
                if isinstance(partial, dict) and partial.get("source") == source_key:
                    initial_sentences = [
                        Sentence.model_validate(item)
                        for item in partial.get("sentences", [])
                    ]
            except (OSError, ValueError, TypeError):
                initial_sentences = []
        offset_samples = (
            initial_sentences[-1].end_sample if initial_sentences else 0
        )

        def persist_partial(sentences: list[Sentence]) -> None:
            if not source_key:
                return
            partial_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = partial_path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "source": source_key,
                        "sentences": [
                            sentence.model_dump(mode="json") for sentence in sentences
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            temporary.replace(partial_path)

        partial_sentences = list(initial_sentences)

        def on_segment(sentence: Sentence) -> None:
            partial_sentences.append(sentence)
            persist_partial(partial_sentences)

        io.report(20, "Preparing speech-to-text")
        large_model = options.model_size in {
            "large-v2",
            "large-v3",
            "large-v3-turbo",
        } or any(
            size in options.model_id
            for size in ("large-v2", "large-v3", "large-v3-turbo")
        )
        if mode == "faster_whisper" and options.device == "cpu" and large_model:
            io.emit(
                "warning",
                "Large Whisper models are very slow on CPU; use a small or medium "
                "model, or a CUDA device.",
                module="transcribe",
            )
        client = io.asr_client
        if client is None:
            if mode == "http":
                base_url = options.base_url or os.environ.get("VIDEOWFLOW_ASR_BASE_URL")
                if not base_url:
                    raise TranscriptionError("HTTP transcription requires base_url")
                client = WhisperHttpAdapter(
                    base_url=base_url,
                    model=options.model,
                    api_key=get_secret(options.api_key_env),
                    language=options.language,
                )
            elif mode == "whisper_cpp":
                client = WhisperCliAdapter(
                    binary=options.whisper_binary or os.environ.get("VIDEOWFLOW_WHISPER_BIN"),
                    model=model_path
                    or options.whisper_model
                    or os.environ.get("VIDEOWFLOW_WHISPER_MODEL"),
                    language=options.language,
                    threads=options.cpu_threads or None,
                    beam_size=options.beam_size or 1,
                    word_timestamps=options.word_timestamps != "off",
                    vulkan=options.quality_profile == "vulkan",
                    log=lambda level, message: io.emit(level, message, module="transcribe"),
                )
            else:
                client = FasterWhisperAdapter(
                    model=model_path,
                    model_size=options.model_size,
                    device=options.device,
                    compute_type=options.compute_type,
                    language=options.language,
                    vad_filter=bool(options.vad_filter),
                    beam_size=options.beam_size or 1,
                    threads=options.cpu_threads or None,
                    word_timestamps=options.word_timestamps != "off",
                    condition_on_previous_text=bool(options.condition_on_previous_text),
                    log=lambda level, message: io.emit(level, message, module="transcribe"),
                )
        io.report(45, "Calling speech-to-text")
        adapter = adapter_for(context, io)
        audio_path = Path(context.source)
        if options.audio_source == "master":
            audio_path = Path(context.artifacts.get("audio_master") or context.source)
        elif options.audio_source == "isolated":
            audio_path = Path(context.artifacts.get("audio_isolated") or context.source)
        wav = adapter.extract_pcm(
            audio_path, context.work / "transcribe.wav", sample_rate=16000
        )
        next_log = [50]

        def on_progress(done: float, total: float) -> None:
            if total <= 0:
                return
            fraction = max(0.0, min(1.0, done / total))
            percent = 45 + int(round(54 * fraction))
            io.report(percent, f"Transcribed {done:.0f}s of {total:.0f}s")
            if percent >= next_log[0]:
                io.emit(
                    "info",
                    f"Transcribing {int(fraction * 100)}% "
                    f"({done:.0f}s of {total:.0f}s)",
                    module="transcribe",
                )
                next_log[0] = percent + 10

        transcribe_kwargs: dict[str, object] = {}
        if _supports_keyword(client.transcribe, "on_progress"):
            transcribe_kwargs["on_progress"] = on_progress
        if _supports_keyword(client.transcribe, "on_segment"):
            transcribe_kwargs["on_segment"] = on_segment
        if _supports_keyword(client.transcribe, "initial_sentences"):
            transcribe_kwargs["initial_sentences"] = initial_sentences
        if _supports_keyword(client.transcribe, "offset_samples"):
            transcribe_kwargs["offset_samples"] = offset_samples
        transcript = client.transcribe(
            wav, media.audio_sample_rate, **transcribe_kwargs
        )
        if not transcript:
            raise TranscriptionError("Speech-to-text returned no sentences")
        context.transcript = list(transcript)
        if source_key:
            partial_path.unlink(missing_ok=True)
        context.transcript_source = mode
        context.hashes["transcribe"] = digest_payload(
            [sentence.model_dump(mode="json") for sentence in transcript]
        )
        if key:
            cache_put(
                "transcript",
                key,
                {
                    "sentences": [sentence.model_dump(mode="json") for sentence in transcript],
                    "source": mode,
                },
            )
        io.emit("info", f"{len(transcript)} sentences from {mode}")
        io.report(100, "Transcript ready")

    @staticmethod
    def _available_mode(context: PipelineContext, io: StepIO) -> Mode:
        for size in ("tiny", "base", "small", "medium", "large-v3"):
            if FasterWhisperAdapter.available(size):  # type: ignore[arg-type]
                return "faster_whisper"
        try:
            from videoflow.application.models import list_models
            from videoflow.runtime import find_whisper_binary

            installed_whisper = any(
                str(item.get("capability")) == "asr"
                and str(item.get("kind")) == "whisper"
                and bool(item.get("installed"))
                for item in list_models()
            )
        except Exception:
            installed_whisper = False
        if (
            os.environ.get("VIDEOWFLOW_WHISPER_BIN")
            or os.environ.get("VIDEOWFLOW_WHISPER_MODEL")
            or (installed_whisper and find_whisper_binary())
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
