"""Local whisper.cpp CLI adapter.

The portable build bundles ``whisper-cli`` and a tiny GGML model. The adapter
writes an SRT with the CLI and reuses the existing SRT parser, so timestamps go
through the same source-sample conversion as an imported subtitle.
"""

from __future__ import annotations

import os
import subprocess
import wave
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from videoflow.domain.errors import TranscriptError, TranscriptionError
from videoflow.domain.state import Sentence
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
        timeout: float = 3600.0,
        log: Callable[[str, str], None] | None = None,
    ) -> None:
        self.binary = Path(binary) if binary else _default_binary()
        self.model = Path(model) if model else _default_model()
        self.language = language
        self.threads = threads or max(1, min(4, os.cpu_count() or 1))
        self.timeout = timeout
        self._log = log

    def transcribe(self, wav_path: Path, sample_rate: int) -> list[Sentence]:
        source = Path(wav_path).expanduser()
        if not source.is_file():
            raise TranscriptionError(f"Audio does not exist: {source}")
        if sample_rate <= 0:
            raise TranscriptionError("sample rate must be positive")
        _require_16k(source)
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
            "-osrt",
            "-of",
            str(prefix),
            "-l",
            self.language,
            "-t",
            str(self.threads),
        ]
        if self._log is not None:
            self._log("debug", "$ " + " ".join(command))
        srt = Path(str(prefix) + ".srt")
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
            if not srt.is_file():
                raise TranscriptionError("whisper-cli did not write an SRT")
            try:
                sentences = parse_srt(srt.read_text(encoding="utf-8-sig"), sample_rate)
            except TranscriptError as exc:
                raise TranscriptionError(f"whisper-cli wrote an invalid SRT: {exc}") from exc
        finally:
            srt.unlink(missing_ok=True)
        if not sentences:
            raise TranscriptionError("whisper-cli returned an empty transcript")
        return sentences


def _default_binary() -> Path:
    found = find_whisper_binary()
    return Path(found) if found else Path("whisper-cli")


def _default_model() -> Path:
    found = find_whisper_model()
    return found if found else Path("ggml-tiny.bin")


def _require_16k(path: Path) -> None:
    try:
        with wave.open(str(path), "rb") as audio:
            rate = audio.getframerate()
    except (wave.Error, OSError, EOFError) as exc:
        raise TranscriptionError(f"Cannot read WAV header: {path}") from exc
    if rate != 16000:
        raise TranscriptionError(f"whisper.cpp needs 16 kHz audio, got {rate} Hz")
