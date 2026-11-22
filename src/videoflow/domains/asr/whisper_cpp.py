"""Local whisper.cpp CLI adapter.

The portable build bundles ``whisper-cli`` and a tiny GGML model. The adapter
writes an SRT or a token JSON with the CLI and reuses the shared parsers, so
timestamps go through the same source-sample conversion as imported subtitles.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import wave
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from videoflow.domain.errors import TranscriptError, TranscriptionError
from videoflow.domain.state import Sentence, WordTiming
from videoflow.domain.transcript import parse_srt
from videoflow.runtime import find_whisper_binary, find_whisper_model


class WhisperCliAdapter:
    def __init__(
        self,
        *,
        binary: str | Path | None = None,
        model: str | Path | None = None,
        language: str = "pt",
        threads: int | None = None,
        beam_size: int = 1,
        word_timestamps: bool = True,
        vulkan: bool = False,
        timeout: float = 3600.0,
        log: Callable[[str, str], None] | None = None,
    ) -> None:
        self.binary = Path(binary) if binary else _default_binary()
        self.model = Path(model) if model else _default_model()
        self.language = language
        self.threads = threads or max(1, min(8, (os.cpu_count() or 2) // 2 or 1))
        self.beam_size = max(1, beam_size)
        self.word_timestamps = word_timestamps
        self.vulkan = vulkan
        self.timeout = timeout
        self._log = log
        self.last_language = ""
        self.last_language_probability = 0.0

    def transcribe(self, wav_path: Path, sample_rate: int) -> list[Sentence]:
        source = Path(wav_path).expanduser()
        if not source.is_file():
            raise TranscriptionError(f"Audio does not exist: {source}")
        if sample_rate <= 0:
            raise TranscriptionError("sample rate must be positive")
        _require_whisper_16k(source)
        if not self.binary.is_file():
            raise TranscriptionError(
                f"whisper-cli was not found: {self.binary}. "
                "Set VIDEOWFLOW_WHISPER_BIN or build with --with-whisper."
            )
        if not self.model.is_file():
            raise TranscriptionError(
                f"Whisper model was not found: {self.model}. "
                "Set VIDEOWFLOW_WHISPER_MODEL or build with --with-whisper."
            )
        prefix = source.parent / f".whisper-{uuid4().hex}"
        command = [
            str(self.binary),
            "-m",
            str(self.model),
            "-f",
            str(source),
            "-of",
            str(prefix),
            "-l",
            self.language,
            "-t",
            str(self.threads),
            "-bs",
            str(self.beam_size),
            "-ojf" if self.word_timestamps else "-osrt",
        ]
        if self.vulkan:
            command.append("-fa")
        else:
            command.append("-ng")
        if self._log is not None:
            self._log("debug", "$ " + " ".join(command))
        srt = Path(str(prefix) + ".srt")
        words_json = Path(str(prefix) + ".json")
        try:
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise TranscriptionError("whisper-cli timed out") from exc
            if completed.returncode != 0:
                tail = " ".join(completed.stderr.strip().splitlines()[-4:])
                if self._log is not None:
                    self._log("error", tail or "whisper-cli failed")
                raise TranscriptionError(f"whisper-cli failed: {tail or 'unknown error'}")
            diagnostics = completed.stdout + completed.stderr
            detected = re.search(r"auto-detected language:\s*([A-Za-z-]{2,12})", diagnostics)
            if detected:
                self.last_language = detected.group(1).casefold()
            probability = re.search(r"auto-detected language:.*?p\s*=\s*([0-9.]+)", diagnostics)
            if probability:
                try:
                    self.last_language_probability = float(probability.group(1))
                except ValueError:
                    self.last_language_probability = 0.0
            if self.word_timestamps and words_json.is_file():
                try:
                    sentences = _parse_json_words(
                        words_json.read_text(encoding="utf-8-sig"), sample_rate
                    )
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    raise TranscriptionError(
                        f"whisper-cli wrote invalid word timestamps: {exc}"
                    ) from exc
            elif srt.is_file():
                try:
                    sentences = parse_srt(srt.read_text(encoding="utf-8-sig"), sample_rate)
                except TranscriptError as exc:
                    raise TranscriptionError(f"whisper-cli wrote an invalid SRT: {exc}") from exc
            else:
                raise TranscriptionError("whisper-cli did not write a transcript")
        finally:
            srt.unlink(missing_ok=True)
            words_json.unlink(missing_ok=True)
        if not sentences:
            raise TranscriptionError("whisper-cli returned an empty transcript")
        return sentences


def _default_binary() -> Path:
    found = find_whisper_binary()
    return Path(found) if found else Path("whisper-cli")


def _default_model() -> Path:
    found = find_whisper_model()
    return found if found else Path("ggml-tiny.bin")


def _require_whisper_16k(path: Path) -> None:
    try:
        with wave.open(str(path), "rb") as audio:
            rate = audio.getframerate()
    except (wave.Error, OSError, EOFError) as exc:
        raise TranscriptionError(f"Cannot read WAV header: {path}") from exc
    if rate != 16000:
        raise TranscriptionError(f"whisper.cpp needs 16 kHz audio, got {rate} Hz")


def _parse_json_words(payload: str, sample_rate: int) -> list[Sentence]:
    """Convert whisper.cpp full JSON tokens into sentence/word timings."""

    data = json.loads(payload)
    transcription = data.get("transcription") if isinstance(data, dict) else None
    words: list[tuple[str, int, int]] = []

    def flush(text: str, start_ms: int, end_ms: int) -> None:
        value = text.strip()
        if not value:
            return
        start = round(max(0, start_ms) * sample_rate / 1000)
        end = round(max(start_ms, end_ms) * sample_rate / 1000)
        words.append((value, start, max(start, end)))

    for segment in transcription if isinstance(transcription, list) else []:
        if not isinstance(segment, dict):
            continue
        offsets = segment.get("offsets") or {}
        segment_start = int(offsets.get("from") or 0)
        segment_end = int(offsets.get("to") or segment_start)
        current = ""
        current_start = segment_start
        current_end = segment_end
        for token in segment.get("tokens") or []:
            if not isinstance(token, dict):
                continue
            text = str(token.get("text") or "")
            if not text or "<|" in text or text.startswith("[_"):
                continue
            token_offsets = token.get("offsets") or {}
            start_ms = int(token_offsets.get("from") or segment_start)
            end_ms = int(token_offsets.get("to") or start_ms)
            if text.startswith(" ") or not current:
                flush(current, current_start, current_end)
                current = text
                current_start = start_ms
                current_end = end_ms
            else:
                current += text
                current_end = end_ms
        flush(current, current_start, current_end)

    if not words:
        raise ValueError("no usable words")
    sentences: list[Sentence] = []
    current_words: list[WordTiming] = []
    for value, start, end in words:
        current_words.append(
            WordTiming(word=value, start_sample=start, end_sample=end, probability=1.0)
        )
        if len(current_words) >= 18 or value.endswith((".", "!", "?", "…", "。", "！", "？")):
            sentences.append(_sentence_from_words(len(sentences), current_words))
            current_words = []
    if current_words:
        sentences.append(_sentence_from_words(len(sentences), current_words))
    return sentences


def _sentence_from_words(identifier: int, words: list[WordTiming]) -> Sentence:
    return Sentence(
        id=identifier,
        start_sample=words[0].start_sample,
        end_sample=max(word.end_sample for word in words),
        text=" ".join(word.word for word in words),
        words=words,
    )
