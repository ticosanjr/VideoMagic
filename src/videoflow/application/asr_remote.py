"""Remote ASR through the VideoFlow compute router.

The client keeps the existing WordTiming contract and treats the worker
transcript as data. It is intentionally a thin adapter so a local
Faster-Whisper run remains the fallback when the worker is offline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from videoflow.domain.errors import TranscriptionError
from videoflow.domain.state import Sentence, WordTiming


class RemoteAsrClient:
    """Submit 16 kHz WAV audio to the GPU worker and parse its transcript."""

    def __init__(
        self,
        router: Any,
        *,
        language: str = "pt",
        model: str = "large-v3-turbo",
        beam_size: int = 1,
        word_timestamps: bool = True,
        vad_filter: bool = True,
        no_speech_threshold: float = 0.6,
        compression_ratio_threshold: float = 2.2,
        repetition_penalty: float = 1.1,
        timeout_sec: float = 1800.0,
        capability: str = "asr",
    ) -> None:
        self.router = router
        self.capability = capability
        self.language = language
        self.model = model
        self.beam_size = beam_size
        self.word_timestamps = word_timestamps
        self.vad_filter = vad_filter
        self.no_speech_threshold = no_speech_threshold
        self.compression_ratio_threshold = compression_ratio_threshold
        self.repetition_penalty = repetition_penalty
        self.timeout_sec = timeout_sec
        self.last_language = ""
        self.last_language_probability = 0.0
        self.execution: dict[str, Any] = {}

    def transcribe(
        self,
        wav_path: Path,
        sample_rate: int,
        **_: Any,
    ) -> list[Sentence]:
        result = self.router.submit(
            self.capability,
            {
                "inputs": [str(wav_path)],
                "language": self.language,
                "model": self.model,
                "beam_size": self.beam_size,
                "word_timestamps": self.word_timestamps,
                "vad_filter": self.vad_filter,
                "condition_on_previous_text": False,
                "no_speech_threshold": self.no_speech_threshold,
                "compression_ratio_threshold": self.compression_ratio_threshold,
                "repetition_penalty": self.repetition_penalty,
                "timeout_sec": self.timeout_sec,
            },
            timeout=self.timeout_sec,
        )
        self.execution = dict(result.get("execution") or {})
        payload = _read_payload(result)
        self.last_language = str(payload.get("language") or "")
        try:
            self.last_language_probability = float(
                payload.get("language_probability") or 0.0
            )
        except (TypeError, ValueError):
            self.last_language_probability = 0.0
        sentences = _sentences(payload, sample_rate)
        if not sentences:
            raise TranscriptionError("remote ASR returned no sentences")
        return sentences


def _read_payload(result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result.get("data"), (bytes, bytearray)):
        raw = bytes(result["data"])
    else:
        path = result.get("path")
        if not path and result.get("paths"):
            path = result["paths"][0]
        if not path:
            raise TranscriptionError("remote ASR returned no transcript artifact")
        target = Path(str(path))
        if not target.is_file():
            raise TranscriptionError(f"remote ASR artifact is missing: {target}")
        raw = target.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise TranscriptionError(f"remote ASR returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise TranscriptionError("remote ASR payload must be a JSON object")
    return payload


def _sentences(payload: dict[str, Any], sample_rate: int) -> list[Sentence]:
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list):
        raw_segments = payload.get("transcription")
    if not isinstance(raw_segments, list):
        return []
    sentences: list[Sentence] = []
    for index, item in enumerate(raw_segments):
        if not isinstance(item, dict):
            continue
        start = _samples(item.get("start"), sample_rate)
        end = _samples(item.get("end"), sample_rate)
        if end <= start:
            continue
        words: list[WordTiming] = []
        for word in item.get("words") or []:
            if not isinstance(word, dict) or not str(word.get("word") or "").strip():
                continue
            word_start = _samples(word.get("start"), sample_rate)
            word_end = _samples(word.get("end"), sample_rate)
            if word_end <= word_start:
                continue
            words.append(
                WordTiming(
                    word=str(word["word"]).strip(),
                    start_sample=word_start,
                    end_sample=word_end,
                    probability=_probability(word.get("probability")),
                )
            )
        text = str(item.get("text") or "").strip()
        if not text and words:
            text = " ".join(word.word for word in words)
        if not text:
            continue
        sentences.append(
            Sentence(
                id=index,
                start_sample=start,
                end_sample=end,
                text=text,
                words=words,
            )
        )
    return sentences


def _samples(value: object, sample_rate: int) -> int:
    try:
        return max(0, round(float(value or 0.0) * sample_rate))
    except (TypeError, ValueError):
        return 0


def _probability(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value or 0.0)))
    except (TypeError, ValueError):
        return 0.0
