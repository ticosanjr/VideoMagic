"""Local Faster-Whisper adapter.

Faster-Whisper runs Whisper through CTranslate2 and exposes word timestamps.
The adapter always transcribes the full 16 kHz WAV, converts word seconds to
source sample indices with exact rational arithmetic, and never downloads a
model implicitly.
"""

from __future__ import annotations

import importlib.util
import os
import wave
from collections.abc import Callable, Iterable
from fractions import Fraction
from pathlib import Path
from typing import Any

from videoflow.domain.config import (
    ComputeDevice,
    ComputeType,
    MediaLanguage,
    ModelSize,
)
from videoflow.domain.errors import JobCancelledError, TranscriptionError
from videoflow.domain.state import Sentence, WordTiming
from videoflow.domain.timebase import Rounding
from videoflow.runtime import (
    FASTER_WHISPER_MODEL_MB,
    expected_faster_whisper_model,
    find_faster_whisper_model,
)

SAMPLE_RATE = 16000


class FasterWhisperAdapter:
    def __init__(
        self,
        *,
        model: str | Path | None = None,
        model_size: ModelSize = "small",
        device: ComputeDevice = "cpu",
        compute_type: ComputeType = "int8",
        language: MediaLanguage = "pt",
        vad_filter: bool = False,
        beam_size: int = 5,
        threads: int | None = None,
        log: Callable[[str, str], None] | None = None,
    ) -> None:
        self.model = Path(model).expanduser() if model is not None else None
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.vad_filter = vad_filter
        self.beam_size = beam_size
        self.threads = threads or max(1, min(4, os.cpu_count() or 1))
        self._log = log
        self._engine: Any | None = None

    @staticmethod
    def available(
        model_size: ModelSize = "small",
        *,
        model: str | Path | None = None,
    ) -> bool:
        """Whether the optional package and a local model directory are present."""

        if model is not None:
            path = Path(model).expanduser()
            found = _is_model_dir(path)
        else:
            found = find_faster_whisper_model(model_size) is not None
        if not found:
            return False
        return importlib.util.find_spec("faster_whisper") is not None

    def transcribe(
        self,
        wav_path: Path,
        sample_rate: int,
        *,
        on_progress: Callable[[float, float], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
        on_segment: Callable[[Sentence], None] | None = None,
        initial_sentences: list[Sentence] | None = None,
        offset_samples: int = 0,
    ) -> list[Sentence]:
        source = Path(wav_path).expanduser()
        if not source.is_file():
            raise TranscriptionError(f"Audio does not exist: {source}")
        if sample_rate <= 0:
            raise TranscriptionError("sample rate must be positive")
        frames = _require_16k(source)
        if self.language not in {"pt", "it", "en", "es", "auto"}:
            raise TranscriptionError(f"Unsupported transcription language: {self.language}")
        if self.beam_size < 1:
            raise TranscriptionError("beam size must be positive")
        model_path = self._resolve_model()
        engine = self._load_engine(model_path)
        initial = list(initial_sentences or [])
        offset = max(0, int(offset_samples))
        offset_16k = int(offset * SAMPLE_RATE / sample_rate)
        transcribe_path = source
        if offset_16k > 0:
            if offset_16k >= frames:
                if initial:
                    return initial
                raise TranscriptionError("Faster-Whisper resume offset is past the audio.")
            tail = _tail_wav(source, offset_16k)
            if tail is not None:
                transcribe_path = tail
        try:
            segments, _info = engine.transcribe(
                str(transcribe_path),
                language=None if self.language == "auto" else self.language,
                beam_size=self.beam_size,
                word_timestamps=True,
                vad_filter=self.vad_filter,
            )
            duration = frames / SAMPLE_RATE if frames > 0 else 0.0
            if duration <= 0:
                duration = float(getattr(_info, "duration", 0.0) or 0.0)
            sentences = _sentences(
                segments,
                sample_rate,
                duration=duration,
                offset_samples=offset,
                initial_sentences=initial,
                on_progress=on_progress,
                on_segment=on_segment,
                should_cancel=should_cancel,
            )
        except JobCancelledError:
            raise
        except TranscriptionError:
            raise
        except Exception as exc:
            if self.device == "cuda":
                raise TranscriptionError(
                    "Faster-Whisper failed on CUDA. Verify the CUDA driver and the "
                    f"CTranslate2 CUDA build, or use device=cpu: {exc}"
                ) from exc
            raise TranscriptionError(f"Faster-Whisper transcription failed: {exc}") from exc
        if not sentences:
            raise TranscriptionError("Faster-Whisper returned an empty transcript")
        return sentences

    def _resolve_model(self) -> Path:
        if self.model is not None:
            path = self.model
        else:
            found = find_faster_whisper_model(self.model_size)
            path = found if found is not None else expected_faster_whisper_model(self.model_size)
        if not _is_model_dir(path):
            size_mb = FASTER_WHISPER_MODEL_MB.get(self.model_size, 0)
            size = f" (~{size_mb} MB)" if size_mb else ""
            raise TranscriptionError(
                f"Faster-Whisper model '{self.model_size}' was not found: {path}{size}. "
                "Run scripts/fetch_faster_whisper.py, set "
                "VIDEOWFLOW_FASTER_WHISPER_MODEL, or build with --with-faster-whisper."
            )
        return path

    def _load_engine(self, model_path: Path) -> Any:
        if self._engine is not None:
            return self._engine
        try:
            from faster_whisper import WhisperModel
        except (ImportError, OSError) as exc:
            raise TranscriptionError(
                "Faster-Whisper requires the optional faster-whisper package. "
                "Install the faster-whisper extra, or use --whisper-engine whisper.cpp."
            ) from exc
        try:
            self._engine = WhisperModel(
                str(model_path),
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=self.threads,
                local_files_only=True,
            )
        except Exception as exc:
            if self.device == "cuda":
                raise TranscriptionError(
                    "Faster-Whisper could not start on CUDA. Verify the CUDA driver and "
                    f"the CTranslate2 CUDA build, or use device=cpu: {exc}"
                ) from exc
            raise TranscriptionError(
                f"Faster-Whisper could not load {model_path} with "
                f"device={self.device}, compute_type={self.compute_type}: {exc}"
            ) from exc
        if self._log is not None:
            self._log("debug", f"Faster-Whisper model loaded: {model_path}")
        return self._engine


def _sentences(
    segments: Iterable[Any],
    sample_rate: int,
    *,
    duration: float = 0.0,
    offset_samples: int = 0,
    initial_sentences: list[Sentence] | None = None,
    on_progress: Callable[[float, float], None] | None = None,
    on_segment: Callable[[Sentence], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[Sentence]:
    sentences: list[Sentence] = list(initial_sentences or [])
    for segment in segments:
        if should_cancel is not None and should_cancel():
            raise JobCancelledError("Job cancelled")
        text = str(getattr(segment, "text", "") or "").strip()
        if not text:
            continue
        raw_words = getattr(segment, "words", None)
        if not raw_words:
            raise TranscriptionError(
                f"Faster-Whisper returned no word timestamps for: {_preview(text)}"
            )
        words: list[WordTiming] = []
        for item in raw_words:
            word = str(getattr(item, "word", "") or "").strip()
            if not word:
                continue
            try:
                start = _samples(item.start, sample_rate, Rounding.FLOOR) + offset_samples
                end = _samples(item.end, sample_rate, Rounding.CEIL) + offset_samples
            except (AttributeError, TypeError, ValueError) as exc:
                raise TranscriptionError(
                    f"Faster-Whisper returned an invalid word timestamp for: {_preview(word)}"
                ) from exc
            if end < start:
                raise TranscriptionError(
                    f"Faster-Whisper returned a word that ends before it starts: {_preview(word)}"
                )
            words.append(
                WordTiming(
                    word=word,
                    start_sample=start,
                    end_sample=end,
                    probability=_probability(getattr(item, "probability", 1.0)),
                )
            )
        if not words:
            raise TranscriptionError(
                f"Faster-Whisper returned no usable word timestamps for: {_preview(text)}"
            )
        start_sample = words[0].start_sample
        end_sample = max(word.end_sample for word in words)
        if end_sample < start_sample:
            raise TranscriptionError(
                f"Faster-Whisper returned a sentence that ends before it starts: {_preview(text)}"
            )
        sentence = Sentence(
            id=len(sentences),
            start_sample=start_sample,
            end_sample=end_sample,
            text=text,
            words=words,
        )
        sentences.append(sentence)
        if on_segment is not None:
            on_segment(sentence)
        if on_progress is not None:
            elapsed = end_sample / sample_rate
            if duration > 0:
                elapsed = min(elapsed, duration)
            on_progress(elapsed, duration)
    return sentences


def _samples(value: object, sample_rate: int, rounding: Rounding) -> int:
    try:
        seconds = Fraction(str(value))
    except (ValueError, TypeError, ZeroDivisionError) as exc:
        raise ValueError(f"invalid timestamp: {value!r}") from exc
    if seconds < 0:
        raise ValueError("negative timestamp")
    scaled = seconds * sample_rate
    if rounding is Rounding.FLOOR:
        return scaled.numerator // scaled.denominator
    return -(-scaled.numerator // scaled.denominator)


def _probability(value: object) -> float:
    try:
        probability = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1.0
    return max(0.0, min(1.0, probability))


def _preview(text: str) -> str:
    normalized = " ".join(text.split())
    return normalized[:80] + ("..." if len(normalized) > 80 else "")


def _is_model_dir(path: Path) -> bool:
    return path.is_dir() and (path / "model.bin").is_file() and (path / "config.json").is_file()


def _tail_wav(path: Path, start_frame: int) -> Path | None:
    """Write a temporary 16 kHz WAV starting at ``start_frame``."""

    try:
        with wave.open(str(path), "rb") as audio:
            frames = audio.getnframes()
            if start_frame <= 0 or start_frame >= frames:
                return None
            params = audio.getparams()
            audio.setpos(start_frame)
            payload = audio.readframes(frames - start_frame)
    except (wave.Error, OSError, EOFError):
        return None
    target = path.with_name(f"{path.stem}.resume.wav")
    try:
        with wave.open(str(target), "wb") as audio:
            audio.setparams(params)
            audio.writeframes(payload)
    except (wave.Error, OSError):
        return None
    return target


def _require_16k(path: Path) -> int:
    try:
        with wave.open(str(path), "rb") as audio:
            rate = audio.getframerate()
            frames = audio.getnframes()
    except (wave.Error, OSError, EOFError) as exc:
        raise TranscriptionError(f"Cannot read WAV header: {path}") from exc
    if rate != SAMPLE_RATE:
        raise TranscriptionError(
            f"Faster-Whisper needs {SAMPLE_RATE // 1000} kHz audio, got {rate} Hz"
        )
    return frames
