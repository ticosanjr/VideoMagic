"""Narration synthesis and word-level alignment for script-first recipes."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.narration import copy_narration, synthesize_narration
from videoflow.application.secrets import get_secret
from videoflow.application.settings import load_settings
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import TranscriptionError, TtsError
from videoflow.domain.state import Sentence
from videoflow.domain.transcript import parse_srt_file
from videoflow.domains.asr.engine import FasterWhisperAdapter
from videoflow.domains.asr.http import WhisperHttpAdapter
from videoflow.domains.asr.legacy_whisper import WhisperCliAdapter
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


def _script_texts(context: PipelineContext) -> list[str]:
    path = context.output / "script" / "script.json"
    payload: object = {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = context.metadata.get("script", {})
    sections = payload.get("sections") if isinstance(payload, dict) else []
    texts = [
        str(item.get("narration") or "").strip()
        for item in sections or []
        if isinstance(item, dict)
    ]
    texts = [text for text in texts if text]
    if texts:
        return texts
    narrative = context.output / "script" / "narration.txt"
    try:
        raw = narrative.read_text(encoding="utf-8").strip()
    except OSError:
        raw = ""
    return [raw] if raw else []


class NarrationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = ""
    profile_id: str = ""
    source_path: str = ""
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    sample_rate: int = Field(default=48000, ge=8000, le=96000)
    output_path: str = Field(default="audio/narration.wav", max_length=2000)


@register_step
class NarrationSynthesizeStep(BaseStep):
    type = "narration.synthesize"
    title = "Synthesize narration"
    description = (
        "Read the approved script and render one narration track with the "
        "configured TTS provider or voice-clone profile."
    )
    status = "available"
    icon = "◍"
    color = "#a78bfa"
    params_model = NarrationParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = NarrationParams.model_validate(params)
        answers = context.metadata.get("hilt_answers", {})
        answer_map = answers.get("answers", {}) if isinstance(answers, dict) else {}
        profile_id = options.profile_id or str(
            answer_map.get("voice_profile_id") or ""
        ).strip()
        source = options.source_path or str(
            answer_map.get("narration_file") or ""
        ).strip()
        target = context.output / options.output_path
        if source:
            result = copy_narration(
                Path(source).expanduser(), target, options.sample_rate
            )
        else:
            texts = _script_texts(context)
            if not texts:
                raise TtsError(
                    "Narration needs an approved script or a narration file."
                )
            result = synthesize_narration(
                texts,
                context.output / "audio" / "narration",
                provider_id=options.provider_id,
                profile_id=profile_id,
                speed=options.speed,
                sample_rate=options.sample_rate,
            )
            if Path(result["path"]) != target:
                target = Path(result["path"])
        if not target.is_file():
            raise TtsError("Narration synthesis did not write an audio file.")
        duration = float(result.get("duration_sec") or 0.0)
        context.artifacts["audio_master"] = str(target)
        context.artifacts["audio_narration"] = str(target)
        context.metadata["narration"] = {**result, "path": str(target)}
        context.metadata["narration_duration_sec"] = duration
        context.hashes["narration.synthesize"] = digest_payload(
            {
                "path": str(target),
                "duration": duration,
                "provider": result.get("provider"),
                "sections": result.get("sections"),
            }
        )
        io.report(100, f"Narration ready ({duration:.1f}s)")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("audio_narration")
        return (Path(path),) if path else ()


class NarrationAlignParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = ""
    mode: str = "auto"
    srt_path: str = ""
    model_size: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str = "pt"
    model_id: str = ""
    base_url: str = ""
    api_key_env: str = "VIDEOWFLOW_ASR_API_KEY"


@register_step
class NarrationAlignStep(BaseStep):
    type = "narration.align"
    title = "Align narration"
    description = (
        "Transcribe the narration track and expose sentence and word timestamps "
        "for the timed storyboard and captions."
    )
    status = "available"
    icon = "⌁"
    color = "#22c55e"
    requires = ("narration.synthesize",)
    params_model = NarrationAlignParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = NarrationAlignParams.model_validate(params)
        narration = Path(
            context.artifacts.get("audio_narration")
            or context.artifacts.get("audio_master")
            or ""
        )
        if not narration.is_file():
            raise TranscriptionError("Narration alignment requires the narration WAV.")
        sample_rate = 48000
        mode = options.mode
        if options.srt_path:
            mode = "srt"
        if mode == "auto":
            mode = self._available_mode()
        io.report(20, "Preparing narration alignment")
        if mode == "srt":
            path = Path(options.srt_path).expanduser()
            sentences = parse_srt_file(path, sample_rate)
        else:
            sentences = self._transcribe(
                narration, sample_rate, options, io, mode
            )
        if not sentences:
            raise TranscriptionError("Narration alignment returned no sentences.")
        target = context.output / "narration" / "transcript.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sentences": [sentence.model_dump(mode="json") for sentence in sentences],
            "sample_rate": sample_rate,
            "duration_sec": max(
                (sentence.end_sample for sentence in sentences), default=0
            )
            / sample_rate,
        }
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        words_path = context.output / "narration" / "words.json"
        words = [
            {
                "word": word.word,
                "start_sec": round(word.start_sample / sample_rate, 3),
                "end_sec": round(word.end_sample / sample_rate, 3),
                "probability": word.probability,
            }
            for sentence in sentences
            for word in sentence.words
        ]
        words_path.write_text(
            json.dumps({"words": words}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        context.transcript = list(sentences)
        context.transcript_source = "narration"
        context.metadata["narration_transcript"] = payload
        context.artifacts["narration_transcript"] = str(target)
        context.artifacts["narration_words"] = str(words_path)
        context.hashes["narration.align"] = digest_payload(
            {"sentences": len(sentences), "words": len(words)}
        )
        io.report(100, f"{len(sentences)} sentence(s), {len(words)} word(s) aligned")

    @staticmethod
    def _available_mode() -> str:
        try:
            import faster_whisper  # noqa: F401

            return "faster_whisper"
        except Exception:
            pass
        try:
            from videoflow.runtime import find_whisper_binary

            if find_whisper_binary():
                return "whisper_cpp"
        except Exception:
            pass
        return "http"

    def _transcribe(
        self,
        path: Path,
        sample_rate: int,
        options: NarrationAlignParams,
        io: StepIO,
        mode: str,
    ) -> list[Sentence]:
        settings = load_settings()
        if mode == "http":
            base_url = options.base_url or settings.llm.base_url
            if not base_url:
                raise TranscriptionError("Narration alignment needs an ASR base URL.")
            client = WhisperHttpAdapter(
                base_url=base_url,
                model="whisper-1",
                api_key=get_secret(options.api_key_env),
                language=options.language,
            )
            return client.transcribe(path, sample_rate)
        if mode == "whisper_cpp":
            from videoflow.runtime import find_whisper_binary, find_whisper_model

            binary = find_whisper_binary()
            model = find_whisper_model()
            if not binary or not model:
                raise TranscriptionError(
                    "Whisper CLI or model was not found; install it or use SRT."
                )
            client = WhisperCliAdapter(
                binary=binary,
                model=str(model),
                language=options.language,
            )
            return client.transcribe(path, sample_rate)
        client = FasterWhisperAdapter(
            model_size=options.model_size,
            device=options.device,
            compute_type=options.compute_type,
            language=options.language,
        )
        return client.transcribe(path, sample_rate)

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("narration_transcript", "narration_words")
            if context.artifacts.get(key)
        )


__all__ = [
    "NarrationAlignParams",
    "NarrationAlignStep",
    "NarrationParams",
    "NarrationSynthesizeStep",
]
