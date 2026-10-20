"""Silero VAD ONNX adapter.

The model is pinned to v5.1.2 and consumes 16 kHz mono PCM in 512-sample
windows. It is the quality path; FFmpeg ``silencedetect`` remains the fallback
when the model or ONNX Runtime is unavailable.
"""

from __future__ import annotations

import os
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

from videoflow.domain.errors import IngestError
from videoflow.runtime import find_silero_model

SAMPLE_RATE = 16000
WINDOW_SAMPLES = 512


class SileroVadAdapter:
    def __init__(
        self,
        model: str | Path | None = None,
        *,
        threshold: float = 0.5,
        min_silence_ms: int = 400,
        min_speech_ms: int = 100,
        threads: int | None = None,
        log: Callable[[str, str], None] | None = None,
    ) -> None:
        self.model = Path(model) if model is not None else _default_model()
        self.threshold = threshold
        self.min_silence_ms = min_silence_ms
        self.min_speech_ms = min_speech_ms
        self.threads = threads or max(1, min(4, os.cpu_count() or 1))
        self._log = log
        self._session: Any | None = None

    @staticmethod
    def available() -> bool:
        """Whether a bundled model and ONNX Runtime are both present."""

        if find_silero_model() is None:
            return False
        try:
            import onnxruntime  # noqa: F401
        except Exception:
            return False
        return True

    def detect(self, wav_path: Path) -> list[tuple[int, int]]:
        """Return speech spans in 16 kHz samples."""

        if not 0.1 <= self.threshold <= 0.9:
            raise IngestError("Silero speech threshold must be between 0.1 and 0.9")
        if min(self.min_silence_ms, self.min_speech_ms) < 0:
            raise IngestError("Silero VAD durations must not be negative")
        samples = _read_wave(Path(wav_path).expanduser())
        if not samples.size:
            raise IngestError("Silero VAD received an empty WAV")
        session = self._load_session()
        try:
            import numpy as np
        except ImportError as exc:  # pragma: no cover - onnxruntime depends on numpy
            raise IngestError("Silero VAD requires numpy.") from exc

        state = np.zeros((2, 1, 128), dtype=np.float32)
        sample_rate = np.array(SAMPLE_RATE, dtype=np.int64)
        active: list[tuple[int, int]] = []
        total = int(samples.size)
        for start in range(0, total, WINDOW_SAMPLES):
            end = min(start + WINDOW_SAMPLES, total)
            chunk = samples[start:end]
            if chunk.size < WINDOW_SAMPLES:
                chunk = np.pad(chunk, (0, WINDOW_SAMPLES - chunk.size))
            try:
                output, state = session.run(
                    ["output", "stateN"],
                    {
                        "input": chunk.reshape(1, -1).astype(np.float32, copy=False),
                        "state": state,
                        "sr": sample_rate,
                    },
                )
            except Exception as exc:  # pragma: no cover - runtime/model failure
                raise IngestError(f"Silero VAD inference failed: {exc}") from exc
            probability = float(output[0][0])
            if probability >= self.threshold:
                active.append((start, end))
            if self._log is not None and start % (WINDOW_SAMPLES * 200) == 0:
                self._log("debug", f"Silero VAD {end}/{total} samples")

        merged = _merge(active, self._gap_samples(self.min_silence_ms))
        minimum = self._gap_samples(self.min_speech_ms)
        merged = [(start, end) for start, end in merged if end - start >= minimum]
        return merged

    def _gap_samples(self, milliseconds: int) -> int:
        return (milliseconds * SAMPLE_RATE + 500) // 1000

    def _load_session(self) -> Any:
        if self._session is not None:
            return self._session
        if not self.model.is_file():
            raise IngestError(
                f"Silero VAD model was not found: {self.model}. "
                "Run scripts/fetch_silero.py, set VIDEOWFLOW_SILERO_MODEL, "
                "or build with --with-silero."
            )
        try:
            import onnxruntime as ort
        except (ImportError, OSError) as exc:
            raise IngestError(
                "Silero VAD requires onnxruntime. Install onnxruntime or use --vad-engine ffmpeg."
            ) from exc
        options = ort.SessionOptions()
        options.intra_op_num_threads = self.threads
        options.log_severity_level = 3
        try:
            session = ort.InferenceSession(
                str(self.model),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        except Exception as exc:
            raise IngestError(f"Cannot load Silero VAD model {self.model}: {exc}") from exc
        inputs = {item.name for item in session.get_inputs()}
        outputs = {item.name for item in session.get_outputs()}
        if not {"input", "state", "sr"} <= inputs or not {"output", "stateN"} <= outputs:
            raise IngestError(
                "Silero VAD model is incompatible; expected the v5.1.2 input and output names."
            )
        self._session = session
        return session


def _default_model() -> Path:
    found = find_silero_model()
    return found if found is not None else Path("silero_vad.onnx")


def _read_wave(path: Path) -> Any:
    if not path.is_file():
        raise IngestError(f"Audio does not exist: {path}")
    try:
        with wave.open(str(path), "rb") as audio:
            if audio.getframerate() != SAMPLE_RATE:
                raise IngestError(
                    f"Silero VAD needs {SAMPLE_RATE} Hz audio, got {audio.getframerate()} Hz"
                )
            if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
                raise IngestError("Silero VAD needs mono 16-bit PCM audio")
            raw = audio.readframes(audio.getnframes())
    except (OSError, wave.Error, EOFError) as exc:
        raise IngestError(f"Cannot read WAV for Silero VAD: {path}: {exc}") from exc
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - onnxruntime depends on numpy
        raise IngestError("Silero VAD requires numpy.") from exc
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def _merge(spans: list[tuple[int, int]], gap: int) -> list[tuple[int, int]]:
    if not spans:
        return []
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and (start <= merged[-1][1] or start - merged[-1][1] < gap):
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
