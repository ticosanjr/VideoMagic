"""External engines. Ingest is implemented; the neural and LLM engines are stubs."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.adapters.llm import OpenAICompatibleLlm
from videoflow.domain.state import MediaInfo


class MediaProbe(Protocol):
    def probe(self, path: Path) -> MediaInfo:
        """Read container metadata without modifying the file."""


class AudioExtractor(Protocol):
    def extract_pcm(self, source: Path, destination: Path) -> Path:
        """Write 16 kHz mono WAV used by VAD and transcription."""


class SpeechDetector(Protocol):
    def detect(self, wav_path: Path) -> list[tuple[int, int]]:
        """Return speech intervals as sample spans."""


class Transcriber(Protocol):
    def transcribe(self, wav_path: Path) -> list[dict[str, object]]:
        """Return sentence dicts with word sample times."""


class LlmClient(Protocol):
    def complete_json(self, prompt: str, schema_name: str) -> dict[str, object]:
        """Call an OpenAI-compatible endpoint and return one JSON object."""


class SileroVadAdapter:
    def detect(self, wav_path: Path) -> list[tuple[int, int]]:
        raise NotImplementedError("Silero VAD is not implemented in this scaffold")


class FasterWhisperAdapter:
    def transcribe(self, wav_path: Path) -> list[dict[str, object]]:
        raise NotImplementedError("Faster-Whisper is not implemented in this scaffold")


__all__ = [
    "AudioExtractor",
    "FFmpegAdapter",
    "FasterWhisperAdapter",
    "LlmClient",
    "MediaProbe",
    "OpenAICompatibleLlm",
    "SileroVadAdapter",
    "SpeechDetector",
    "Transcriber",
]
