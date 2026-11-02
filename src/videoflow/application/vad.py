"""VAD engine selection, Silero rescaling, and sample pads.

Silero runs at 16 kHz, while the pipeline stores every speech span at the source
audio rate. Integer floor/ceil rescaling keeps the mapping exact in rational
time; no floating-point timestamps enter the project.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from videoflow.adapters.silero import SAMPLE_RATE, SileroVadAdapter
from videoflow.domain.config import VadEngine
from videoflow.domain.errors import IngestError
from videoflow.domain.state import MediaInfo
from videoflow.domain.timebase import Rounding
from videoflow.runtime import find_silero_model


@dataclass(frozen=True, slots=True)
class VadDetection:
    spans: list[tuple[int, int]]
    engine: Literal["silero", "ffmpeg"]


def detect_speech(
    engine: Any,
    source: Path,
    work: Path,
    media: MediaInfo,
    *,
    vad_engine: VadEngine = "auto",
    noise_db: float = -30.0,
    min_silence_ms: int = 400,
    min_speech_ms: int = 100,
    speech_threshold: float = 0.5,
    speech_pad_before_ms: int = 120,
    speech_pad_after_ms: int = 150,
    duration_samples: int | None = None,
    apply_pads: bool = True,
    spike_suppression_ms: int = 0,
    merge_gap_ms: int = 0,
    log: Callable[[str, str], None] | None = None,
) -> VadDetection:
    """Detect speech with Silero when available, otherwise FFmpeg.

    ``auto`` never turns a missing optional model into a failed run. An explicit
    ``silero`` request does fail with an actionable message instead of silently
    downgrading quality.
    """

    if vad_engine not in {"auto", "silero", "ffmpeg"}:
        raise IngestError(f"Unknown VAD engine: {vad_engine}")
    duration = (
        duration_samples
        if duration_samples is not None
        else media.timebase().seconds_to_samples(
            media.timebase().frames_to_seconds(media.duration_frames),
            Rounding.NEAREST,
        )
    )
    if vad_engine in {"auto", "silero"}:
        if SileroVadAdapter.available():
            silero = SileroVadAdapter(
                threshold=speech_threshold,
                min_silence_ms=min_silence_ms,
                min_speech_ms=min_speech_ms,
                log=log,
            )
            wav = engine.extract_pcm(
                source,
                work / "vad.wav",
                sample_rate=SAMPLE_RATE,
            )
            raw = silero.detect(wav)
            spans = rescale_spans(raw, SAMPLE_RATE, media.audio_sample_rate, duration)
            if apply_pads:
                spans = pad_spans(
                    spans,
                    media.audio_sample_rate,
                    speech_pad_before_ms,
                    speech_pad_after_ms,
                    duration,
                )
            spans = postprocess_spans(
                spans,
                media.audio_sample_rate,
                spike_suppression_ms=spike_suppression_ms,
                merge_gap_ms=merge_gap_ms,
                duration_samples=duration,
            )
            return VadDetection(spans=spans, engine="silero")
        if vad_engine == "silero":
            raise IngestError(_silero_missing_message())

    spans = engine.detect_speech(
        work / "source.wav",
        duration_samples=duration,
        sample_rate=media.audio_sample_rate,
        noise_db=noise_db,
        min_silence_ms=min_silence_ms,
        min_speech_ms=min_speech_ms,
    )
    if apply_pads:
        spans = pad_spans(
            spans,
            media.audio_sample_rate,
            speech_pad_before_ms,
            speech_pad_after_ms,
            duration,
        )
    spans = postprocess_spans(
        spans,
        media.audio_sample_rate,
        spike_suppression_ms=spike_suppression_ms,
        merge_gap_ms=merge_gap_ms,
        duration_samples=duration,
    )
    return VadDetection(spans=spans, engine="ffmpeg")


def rescale_spans(
    spans: Sequence[tuple[int, int]],
    source_rate: int,
    target_rate: int,
    duration_samples: int | None = None,
) -> list[tuple[int, int]]:
    """Map half-open sample spans between rates without losing coverage."""

    if source_rate <= 0 or target_rate <= 0:
        raise IngestError("sample rates must be positive")
    result: list[tuple[int, int]] = []
    for start, end in spans:
        if end <= start:
            continue
        mapped_start = start * target_rate // source_rate
        mapped_end = (end * target_rate + source_rate - 1) // source_rate
        if duration_samples is not None:
            mapped_start = max(0, min(mapped_start, duration_samples))
            mapped_end = max(0, min(mapped_end, duration_samples))
        if mapped_end > mapped_start:
            result.append((mapped_start, mapped_end))
    return merge_spans(result)


def pad_spans(
    spans: Sequence[tuple[int, int]],
    sample_rate: int,
    before_ms: int,
    after_ms: int,
    duration_samples: int | None = None,
) -> list[tuple[int, int]]:
    """Apply asymmetric pads in samples, clamp, and merge overlaps."""

    if min(before_ms, after_ms) < 0:
        raise IngestError("speech pads must not be negative")
    before = (before_ms * sample_rate + 500) // 1000
    after = (after_ms * sample_rate + 500) // 1000
    padded: list[tuple[int, int]] = []
    for start, end in spans:
        if end <= start:
            continue
        item = (max(0, start - before), end + after)
        if duration_samples is not None:
            item = (min(item[0], duration_samples), min(item[1], duration_samples))
        if item[1] > item[0]:
            padded.append(item)
    return merge_spans(padded)


def postprocess_spans(
    spans: Sequence[tuple[int, int]],
    sample_rate: int,
    *,
    spike_suppression_ms: int = 0,
    merge_gap_ms: int = 0,
    duration_samples: int | None = None,
) -> list[tuple[int, int]]:
    """Drop isolated short sounds and bridge tiny gaps between kept speech."""

    if sample_rate <= 0:
        raise IngestError("sample rate must be positive")
    if spike_suppression_ms < 0 or merge_gap_ms < 0:
        raise IngestError("spike and merge durations must not be negative")
    minimum = (spike_suppression_ms * sample_rate + 500) // 1000
    filtered = [
        (max(0, start), end)
        for start, end in spans
        if end > start and (minimum == 0 or end - start >= minimum)
    ]
    if duration_samples is not None:
        filtered = [
            (min(start, duration_samples), min(end, duration_samples))
            for start, end in filtered
        ]
        filtered = [(start, end) for start, end in filtered if end > start]
    gap = (merge_gap_ms * sample_rate + 500) // 1000
    if gap <= 0:
        return merge_spans(filtered)
    merged: list[tuple[int, int]] = []
    for start, end in sorted(filtered):
        if merged and start - merged[-1][1] <= gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def merge_spans(spans: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def complement_spans(
    spans: Sequence[tuple[int, int]],
    duration_samples: int,
) -> list[tuple[int, int]]:
    """Return the gaps left by ``spans`` inside ``[0, duration_samples)``."""

    if duration_samples <= 0:
        return []
    clipped = [
        (max(0, start), min(duration_samples, end))
        for start, end in spans
        if end > start
    ]
    gaps: list[tuple[int, int]] = []
    cursor = 0
    for start, end in merge_spans(clipped):
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration_samples:
        gaps.append((cursor, duration_samples))
    return gaps


def _silero_missing_message() -> str:
    if find_silero_model() is None:
        return (
            "Silero VAD model was not found. Run scripts/fetch_silero.py, set "
            "VIDEOWFLOW_SILERO_MODEL, or build with --with-silero."
        )
    if importlib.util.find_spec("onnxruntime") is None:
        return "Silero VAD requires onnxruntime. Install onnxruntime or use --vad-engine ffmpeg."
    return (
        "Silero VAD cannot start; ONNX Runtime or the model failed to load. "
        "Use --vad-engine ffmpeg for the fallback."
    )
