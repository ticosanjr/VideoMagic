"""Speech timing diagnostics: word-onset offset and A/V drift.

The compensation is deliberately opt-in. The diagnosis is always written to a
report so a silent shift never changes a transcript without evidence.
"""

from __future__ import annotations

import statistics
import wave
from pathlib import Path

from videoflow.domain.headless import SyncReport
from videoflow.domain.state import Sentence


def onset_offset_ms(
    sentences: list[Sentence],
    speech_intervals: list[tuple[int, int]],
    sample_rate: int,
) -> int:
    """Estimate the systematic word-onset offset from ASR vs VAD starts."""

    if not sentences or not speech_intervals or sample_rate <= 0:
        return 0
    starts = sorted(start for start, _end in speech_intervals)
    deltas: list[float] = []
    for sentence in sentences[:200]:
        if not sentence.words:
            continue
        word_start = min(word.start_sample for word in sentence.words)
        nearest = min(starts, key=lambda start: abs(start - word_start))
        delta = word_start - nearest
        if abs(delta) <= sample_rate:  # ignore wildly unrelated spans
            deltas.append(delta / sample_rate * 1000)
    if not deltas:
        return 0
    return int(round(statistics.median(deltas)))


def _read_wav(path: Path) -> tuple[list[float], int]:
    with wave.open(str(path), "rb") as handle:
        if handle.getsampwidth() != 2 or handle.getnchannels() != 1:
            raise ValueError("drift measurement needs 16-bit mono WAV")
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    samples = [
        int.from_bytes(frames[index : index + 2], "little", signed=True) / 32768.0
        for index in range(0, len(frames), 2)
    ]
    return samples, rate


def detect_drift_ms(
    camera_wav: Path,
    reference_wav: Path,
    *,
    max_shift_sec: float = 2.0,
) -> int | None:
    """Cross-correlate two mono WAV tracks and return the camera delay in ms."""

    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy is a project dependency
        return None
    try:
        left, rate = _read_wav(Path(camera_wav))
        right, right_rate = _read_wav(Path(reference_wav))
    except (OSError, EOFError, ValueError):
        return None
    if rate != right_rate:
        return None
    size = min(len(left), len(right))
    if size < rate // 2:
        return None
    a = np.asarray(left[:size], dtype=np.float32)
    b = np.asarray(right[:size], dtype=np.float32)
    a -= a.mean()
    b -= b.mean()
    max_shift = min(size, int(max_shift_sec * rate))
    step = max(1, size // 4000)
    a = a[::step]
    b = b[::step]
    max_shift = max(1, min(max_shift // step, len(a) // 2))
    best_shift = 0
    best_score = float("-inf")
    for shift in range(-max_shift, max_shift + 1):
        if shift < 0:
            x = a[-shift:]
            y = b[: len(x)]
        elif shift > 0:
            y = b[shift:]
            x = a[: len(y)]
        else:
            x, y = a, b
        score = float(np.dot(x, y)) if len(x) and len(y) else float("-inf")
        if score > best_score:
            best_score = score
            best_shift = shift
    return int(round(best_shift * step / rate * 1000))


def shift_sentences(sentences: list[Sentence], offset_ms: int, sample_rate: int) -> list[Sentence]:
    """Shift words and sentence bounds by ``offset_ms`` without going negative."""

    shift = int(round(offset_ms / 1000 * sample_rate))
    if shift == 0:
        return sentences
    shifted: list[Sentence] = []
    for sentence in sentences:
        words = [
            word.model_copy(
                update={
                    "start_sample": max(0, word.start_sample + shift),
                    "end_sample": max(0, word.end_sample + shift),
                }
            )
            for word in sentence.words
        ]
        shifted.append(
            sentence.model_copy(
                update={
                    "start_sample": max(0, sentence.start_sample + shift),
                    "end_sample": max(0, sentence.end_sample + shift),
                    "words": words,
                }
            )
        )
    return shifted


def report_for(
    *,
    mode: str,
    measured_ms: int,
    threshold_ms: int,
    drift_ms: int = 0,
    reason: str = "",
    sources: list[str] | None = None,
) -> SyncReport:
    if mode == "off":
        applied = False
        reason = reason or "disabled"
    elif mode == "fixed":
        applied = measured_ms != 0
    else:
        applied = abs(measured_ms) >= threshold_ms
        reason = reason or ("threshold_exceeded" if applied else "below_threshold")
    return SyncReport(
        offset_ms=measured_ms,
        drift_ms=drift_ms,
        applied=applied,
        mode=mode,
        reason=reason,
        sources=list(sources or []),
    )
