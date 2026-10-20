"""OpenAI-compatible speech-to-text client.

Works with OpenAI, Groq, a local faster-whisper server, or any endpoint that
implements ``POST /audio/transcriptions`` with ``response_format=verbose_json``.
The API key is never logged or included in an error.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

import httpx

from videoflow.domain.errors import TranscriptionError
from videoflow.domain.state import Sentence, WordTiming


class WhisperHttpAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        model: str = "whisper-1",
        api_key: str | None = None,
        language: str = "pt",
        timeout: float = 300.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key or ""
        self.language = language
        self.timeout = timeout
        self._transport = transport

    def transcribe(self, wav_path: Path, sample_rate: int) -> list[Sentence]:
        source = Path(wav_path).expanduser()
        if not source.is_file():
            raise TranscriptionError(f"Audio does not exist: {source}")
        if sample_rate <= 0:
            raise TranscriptionError("sample rate must be positive")
        data: dict[str, str] = {
            "model": self.model,
            "response_format": "verbose_json",
        }
        if self.language != "auto":
            data["language"] = self.language
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        try:
            with (
                source.open("rb") as audio,
                httpx.Client(timeout=self.timeout, transport=self._transport) as client,
            ):
                response = client.post(
                    f"{self._endpoint()}/audio/transcriptions",
                    headers=headers,
                    data=data,
                    files={"file": (source.name, audio, "audio/wav")},
                )
        except httpx.HTTPError as exc:
            raise TranscriptionError(
                f"Cannot reach the transcription endpoint: {exc.__class__.__name__}"
            ) from exc
        if response.status_code >= 400:
            raise TranscriptionError(
                f"Transcription endpoint returned HTTP {response.status_code}: "
                f"{response.text[:200].strip()}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise TranscriptionError("Transcription endpoint returned invalid JSON") from exc
        return _sentences(payload, sample_rate)

    def _endpoint(self) -> str:
        if self.base_url.endswith("/audio/transcriptions"):
            return self.base_url[: -len("/audio/transcriptions")]
        return self.base_url


def _sentences(payload: Any, sample_rate: int) -> list[Sentence]:
    if not isinstance(payload, dict):
        raise TranscriptionError("Transcription payload is not an object")
    segments = payload.get("segments")
    if not isinstance(segments, list) or not segments:
        raise TranscriptionError(
            "Transcription has no segments. Use response_format=verbose_json."
        )
    sentences: list[Sentence] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start = _samples(segment.get("start"), sample_rate)
        end = _samples(segment.get("end"), sample_rate)
        if end < start:
            continue
        words: list[WordTiming] = []
        raw_words = segment.get("words")
        if isinstance(raw_words, list):
            for item in raw_words:
                if not isinstance(item, dict):
                    continue
                word = str(item.get("word", "")).strip()
                if not word:
                    continue
                word_start = _samples(item.get("start"), sample_rate)
                word_end = _samples(item.get("end"), sample_rate)
                if word_end < word_start:
                    continue
                probability = float(item.get("probability", 1.0))
                words.append(
                    WordTiming(
                        word=word,
                        start_sample=word_start,
                        end_sample=word_end,
                        probability=max(0.0, min(1.0, probability)),
                    )
                )
        sentences.append(
            Sentence(
                id=len(sentences),
                start_sample=start,
                end_sample=max(start, end),
                text=text,
                words=words,
            )
        )
    if not sentences:
        raise TranscriptionError("Transcription contained no usable sentences")
    return sentences


def _samples(value: object, sample_rate: int) -> int:
    try:
        seconds = Fraction(str(value))
    except (ValueError, TypeError) as exc:
        raise TranscriptionError(f"Invalid timestamp: {value!r}") from exc
    if seconds < 0:
        raise TranscriptionError("Transcription timestamp is negative")
    scaled = seconds * sample_rate
    return (scaled.numerator + scaled.denominator // 2) // scaled.denominator
