"""Audio similarity and alignment helpers for cut calibration.

This module is intentionally independent from the editing pipeline. It loads
PCM through FFmpeg, computes log-mel features, and aligns two audio sequences
with dynamic time warping. The primary consumer is the offline calibration
script that compares a rendered cut with the human reference edit.
"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from videoflow.domain.errors import IngestError
from videoflow.runtime import find_binary

SAMPLE_RATE = 16_000
FRAME_LENGTH = 400  # 25 ms
FRAME_HOP = 160  # 10 ms
N_MELS = 64
FMIN = 80.0
FMAX = 7600.0
WINDOW_FRAMES = 100  # 1 s
WINDOW_HOP = 50  # 0.5 s
SEGMENTS = 8
EPSILON = 1e-10


def load_pcm(
    path: Path,
    *,
    sample_rate: int = SAMPLE_RATE,
    timeout: float = 900.0,
) -> np.ndarray:
    """Decode the first audio stream to mono float32 PCM in ``[-1, 1]``."""

    binary = find_binary("ffmpeg")
    if binary is None:
        raise IngestError("FFmpeg is not available for audio comparison.")
    source = Path(path).expanduser()
    if not source.is_file():
        raise IngestError(f"Audio source does not exist: {source}")
    command = [
        binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "-",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IngestError(f"Audio decode failed: {exc}") from exc
    if result.returncode != 0 or not result.stdout:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise IngestError(f"Audio decode produced no PCM: {detail[:300]}")
    samples = np.frombuffer(result.stdout, dtype="<i2")
    if not samples.size:
        raise IngestError("Audio decode produced an empty stream.")
    return (samples.astype(np.float32) / 32768.0).copy()


def _hann(length: int) -> np.ndarray:
    return np.hanning(length).astype(np.float32)


def _hz_to_mel(value: float) -> float:
    return 2595.0 * math.log10(1.0 + value / 700.0)


def _mel_to_hz(value: float) -> float:
    return 700.0 * (10.0 ** (value / 2595.0) - 1.0)


def mel_filterbank(
    *,
    sample_rate: int = SAMPLE_RATE,
    n_fft: int = FRAME_LENGTH,
    n_mels: int = N_MELS,
    fmin: float = FMIN,
    fmax: float = FMAX,
) -> np.ndarray:
    """Return a triangular HTK mel filterbank with area normalisation."""

    low = _hz_to_mel(fmin)
    high = _hz_to_mel(min(fmax, sample_rate / 2))
    points = np.linspace(low, high, n_mels + 2)
    hz_points = np.asarray([_mel_to_hz(value) for value in points])
    bins = np.floor((n_fft + 1) * hz_points / sample_rate).astype(int)
    bins = np.clip(bins, 0, n_fft // 2)
    bank = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for index in range(n_mels):
        left, center, right = int(bins[index]), int(bins[index + 1]), int(bins[index + 2])
        center = max(center, left + 1)
        right = max(right, center + 1)
        for bin_index in range(left, min(center, bank.shape[1])):
            bank[index, bin_index] = (bin_index - left) / (center - left)
        for bin_index in range(center, min(right, bank.shape[1])):
            bank[index, bin_index] = (right - bin_index) / (right - center)
    widths = hz_points[2:] - hz_points[:-2]
    bank *= (2.0 / np.maximum(widths, 1e-6))[:, None]
    return bank


def log_mel(
    pcm: np.ndarray,
    *,
    sample_rate: int = SAMPLE_RATE,
    n_fft: int = FRAME_LENGTH,
    hop: int = FRAME_HOP,
    n_mels: int = N_MELS,
    fmin: float = FMIN,
    fmax: float = FMAX,
    chunk_frames: int = 4000,
) -> np.ndarray:
    """Compute a log-mel spectrogram in chunks to keep memory bounded."""

    signal = np.asarray(pcm, dtype=np.float32)
    if signal.ndim != 1:
        signal = signal.reshape(-1)
    if signal.size < n_fft:
        signal = np.pad(signal, (0, n_fft - signal.size))
    frame_count = 1 + (signal.size - n_fft) // hop
    usable = signal[: (frame_count - 1) * hop + n_fft]
    window = _hann(n_fft)
    bank = mel_filterbank(
        sample_rate=sample_rate,
        n_fft=n_fft,
        n_mels=n_mels,
        fmin=fmin,
        fmax=fmax,
    )
    output = np.empty((frame_count, n_mels), dtype=np.float32)
    for start in range(0, frame_count, chunk_frames):
        end = min(start + chunk_frames, frame_count)
        base = start * hop
        block = usable[base : base + (end - start - 1) * hop + n_fft]
        frames = np.lib.stride_tricks.sliding_window_view(block, n_fft)[::hop]
        spectrum = np.fft.rfft(frames * window, n=n_fft, axis=1)
        power = (spectrum.real**2 + spectrum.imag**2).astype(np.float32)
        mel = power @ bank.T
        output[start:end] = np.log(np.maximum(mel, EPSILON))
    return output


def frame_rms(
    pcm: np.ndarray,
    *,
    frame_length: int = FRAME_HOP,
    hop: int = FRAME_HOP,
) -> np.ndarray:
    """Return RMS per frame, using 10 ms frames by default."""

    signal = np.asarray(pcm, dtype=np.float32)
    if signal.ndim != 1:
        signal = signal.reshape(-1)
    if signal.size < frame_length:
        signal = np.pad(signal, (0, frame_length - signal.size))
    frame_count = 1 + (signal.size - frame_length) // hop
    usable = signal[: (frame_count - 1) * hop + frame_length]
    frames = np.lib.stride_tricks.sliding_window_view(usable, frame_length)[::hop]
    return np.sqrt(np.mean(frames * frames, axis=1)).astype(np.float32)


def speech_fraction(
    pcm: np.ndarray,
    *,
    window_frames: int = WINDOW_FRAMES,
    window_hop: int = WINDOW_HOP,
    threshold_db: float = -40.0,
) -> np.ndarray:
    """Return the fraction of active frames inside each analysis window."""

    rms = frame_rms(pcm)
    if rms.size == 0:
        return np.zeros(0, dtype=np.float32)
    relative = float(np.percentile(rms, 95)) * 0.05
    threshold = max(float(10 ** (threshold_db / 20.0)), relative)
    active = (rms > threshold).astype(np.float32)
    if active.size < window_frames:
        active = np.pad(active, (0, window_frames - active.size))
    windows = np.lib.stride_tricks.sliding_window_view(active, window_frames)[::window_hop]
    return windows.mean(axis=1).astype(np.float32)


def window_descriptors(
    features: np.ndarray,
    *,
    window_frames: int = WINDOW_FRAMES,
    window_hop: int = WINDOW_HOP,
    segments: int = SEGMENTS,
) -> np.ndarray:
    """Describe 1 s windows with per-segment mel mean and deviation.

    Mean-centring and L2 normalisation make the descriptor insensitive to gain
    and loudness differences between the reference and the rendered output.
    """

    data = np.asarray(features, dtype=np.float32)
    if data.ndim != 2:
        raise ValueError("features must be a 2-D matrix")
    if data.shape[0] < window_frames:
        data = np.pad(data, ((0, window_frames - data.shape[0]), (0, 0)), mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(data, window_frames, axis=0)[
        ::window_hop
    ]
    count = windows.shape[0]
    frames_per_segment = max(1, window_frames // segments)
    usable = frames_per_segment * segments
    shaped = windows[:, :, :usable].reshape(
        count, data.shape[1], segments, frames_per_segment
    )
    means = shaped.mean(axis=3)
    deviations = shaped.std(axis=3)
    descriptor = np.concatenate(
        (
            means.transpose(0, 2, 1).reshape(count, -1),
            deviations.transpose(0, 2, 1).reshape(count, -1),
        ),
        axis=1,
    )
    descriptor -= descriptor.mean(axis=1, keepdims=True)
    norm = np.linalg.norm(descriptor, axis=1, keepdims=True)
    descriptor /= np.maximum(norm, 1e-6)
    return descriptor.astype(np.float32)


@dataclass(frozen=True, slots=True)
class AudioFeatures:
    pcm: np.ndarray
    logmel: np.ndarray
    descriptors: np.ndarray
    speech: np.ndarray
    duration: float
    window_seconds: float
    window_hop_seconds: float


def extract_features(
    pcm: np.ndarray,
    *,
    sample_rate: int = SAMPLE_RATE,
    window_frames: int = WINDOW_FRAMES,
    window_hop: int = WINDOW_HOP,
) -> AudioFeatures:
    """Build descriptors and speech fractions for one PCM stream."""

    signal = np.asarray(pcm, dtype=np.float32)
    features = log_mel(signal, sample_rate=sample_rate)
    descriptors = window_descriptors(
        features, window_frames=window_frames, window_hop=window_hop
    )
    speech = speech_fraction(
        signal, window_frames=window_frames, window_hop=window_hop
    )
    count = descriptors.shape[0]
    speech = (
        np.pad(speech, (0, count - speech.size))
        if speech.size < count
        else speech[:count]
    )
    return AudioFeatures(
        pcm=signal,
        logmel=features,
        descriptors=descriptors,
        speech=speech.astype(np.float32),
        duration=signal.size / sample_rate,
        window_seconds=window_frames * FRAME_HOP / sample_rate,
        window_hop_seconds=window_hop * FRAME_HOP / sample_rate,
    )


def _cost_matrix(
    source: np.ndarray,
    target: np.ndarray,
    *,
    source_speech: np.ndarray | None = None,
    target_speech: np.ndarray | None = None,
    speech_penalty: float = 0.0,
) -> np.ndarray:
    similarity = np.clip(source @ target.T, -1.0, 1.0)
    cost = np.clip(1.0 - similarity, 0.0, 2.0).astype(np.float32)
    if (
        speech_penalty > 0
        and source_speech is not None
        and target_speech is not None
    ):
        cost += speech_penalty * np.abs(
            source_speech[:, None] - target_speech[None, :]
        )
    return cost


def _median_filter(values: np.ndarray, size: int = 5) -> np.ndarray:
    if size <= 1 or values.size < size:
        return values.copy()
    half = size // 2
    padded = np.pad(values, (half, half), mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, size)
    return np.median(windows, axis=1)


def dtw_subsequence(
    source: np.ndarray,
    target: np.ndarray,
    *,
    source_speech: np.ndarray | None = None,
    target_speech: np.ndarray | None = None,
    speech_penalty: float = 0.25,
    gap_source: float = 2.0,
) -> tuple[list[tuple[int, int]], float]:
    """Align a short sequence to a subsequence of a longer one.

    Skipping target windows is free; skipping source windows is expensive.
    The result is a monotonic list of ``(source_index, target_index)`` matches.
    """

    source_data = np.asarray(source, dtype=np.float32)
    target_data = np.asarray(target, dtype=np.float32)
    if source_data.ndim != 2 or target_data.ndim != 2:
        raise ValueError("source and target must be 2-D matrices")
    if source_data.shape[0] == 0 or target_data.shape[0] == 0:
        return [], 0.0
    cost = _cost_matrix(
        source_data,
        target_data,
        source_speech=source_speech,
        target_speech=target_speech,
        speech_penalty=speech_penalty,
    )
    n, m = cost.shape
    peak = np.float32(1e9)
    dp = np.full((n, m), peak, dtype=np.float32)
    choice = np.zeros((n, m), dtype=np.uint8)
    dp[0] = np.minimum.accumulate(cost[0])
    for index in range(1, m):
        choice[0, index] = 0 if cost[0, index] <= dp[0, index - 1] else 1
    for row in range(1, n):
        previous = dp[row - 1]
        diagonal = np.full(m, peak, dtype=np.float32)
        diagonal[1:] = previous[:-1] + cost[row, 1:]
        upward = previous + np.float32(gap_source)
        base = np.minimum(diagonal, upward)
        current = np.minimum.accumulate(base)
        left = np.zeros(m, dtype=bool)
        left[1:] = current[:-1] < base[1:]
        choice[row] = np.where(
            left,
            1,
            np.where(diagonal <= upward, 0, 2),
        ).astype(np.uint8)
        dp[row] = current
    column = int(np.argmin(dp[-1]))
    total = float(dp[-1, column])
    row = n - 1
    matches: list[tuple[int, int]] = []
    while row >= 0 and column >= 0:
        direction = int(choice[row, column])
        if direction == 0:
            matches.append((row, column))
            row -= 1
            column -= 1
        elif direction == 1:
            column -= 1
        else:
            row -= 1
    matches.reverse()
    return matches, total


def dtw_symmetric(
    reference: np.ndarray,
    output: np.ndarray,
    *,
    reference_speech: np.ndarray | None = None,
    output_speech: np.ndarray | None = None,
    speech_penalty: float = 0.25,
    gap: float = 0.2,
    band: int | None = None,
) -> list[tuple[int, int]]:
    """Monotonic one-to-one alignment with gap penalties on both sides."""

    reference_data = np.asarray(reference, dtype=np.float32)
    output_data = np.asarray(output, dtype=np.float32)
    if reference_data.ndim != 2 or output_data.ndim != 2:
        raise ValueError("reference and output must be 2-D matrices")
    n, m = reference_data.shape[0], output_data.shape[0]
    if n == 0 or m == 0:
        return []
    cost = _cost_matrix(
        reference_data,
        output_data,
        source_speech=reference_speech,
        target_speech=output_speech,
        speech_penalty=speech_penalty,
    )
    peak = np.float32(1e9)
    dp = np.full((n, m), peak, dtype=np.float32)
    choice = np.zeros((n, m), dtype=np.uint8)
    dp[0, 0] = cost[0, 0]
    for column in range(1, m):
        dp[0, column] = dp[0, column - 1] + np.float32(gap)
        choice[0, column] = 1
    for row in range(1, n):
        dp[row, 0] = dp[row - 1, 0] + np.float32(gap)
        choice[row, 0] = 2
    for row in range(1, n):
        low = 1 if band is None else max(1, row - band)
        high = m - 1 if band is None else min(m - 1, row + band)
        if low > high:
            continue
        previous = dp[row - 1]
        columns = np.arange(low, high + 1)
        diagonal = previous[low - 1 : high] + cost[row, low : high + 1]
        upward = previous[low : high + 1] + np.float32(gap)
        base = np.minimum(diagonal, upward)
        row_values = np.minimum.accumulate(
            base - columns.astype(np.float32) * np.float32(gap)
        ) + columns.astype(np.float32) * np.float32(gap)
        left = np.zeros(row_values.size, dtype=bool)
        if row_values.size > 1:
            left[1:] = row_values[:-1] < base[1:]
        dp[row, low : high + 1] = row_values
        choice[row, low : high + 1] = np.where(
            left,
            1,
            np.where(diagonal <= upward, 0, 2),
        ).astype(np.uint8)
    row, column = n - 1, m - 1
    matches: list[tuple[int, int]] = []
    while row >= 0 and column >= 0:
        direction = int(choice[row, column])
        if direction == 0:
            matches.append((row, column))
            row -= 1
            column -= 1
        elif direction == 1:
            column -= 1
        else:
            row -= 1
    matches.reverse()
    return matches


@dataclass(frozen=True, slots=True)
class AudioComparison:
    audio_f1: float
    audio_f1_all: float
    coverage_reference: float
    coverage_output: float
    coverage_reference_all: float
    coverage_output_all: float
    mean_similarity: float
    median_similarity: float
    p10_similarity: float
    matched_windows: int
    reference_windows: int
    output_windows: int
    matched_seconds: float
    reference_seconds: float
    output_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "audio_f1": round(self.audio_f1, 6),
            "audio_f1_all": round(self.audio_f1_all, 6),
            "coverage_reference": round(self.coverage_reference, 6),
            "coverage_output": round(self.coverage_output, 6),
            "coverage_reference_all": round(self.coverage_reference_all, 6),
            "coverage_output_all": round(self.coverage_output_all, 6),
            "mean_similarity": round(self.mean_similarity, 6),
            "median_similarity": round(self.median_similarity, 6),
            "p10_similarity": round(self.p10_similarity, 6),
            "matched_windows": self.matched_windows,
            "reference_windows": self.reference_windows,
            "output_windows": self.output_windows,
            "matched_seconds": round(self.matched_seconds, 3),
            "reference_seconds": round(self.reference_seconds, 3),
            "output_seconds": round(self.output_seconds, 3),
        }


def compare_audio(
    reference_pcm: np.ndarray,
    output_pcm: np.ndarray,
    *,
    tau: float = 0.9,
    speech_penalty: float = 0.25,
    band: int | None = None,
    speech_threshold: float = 0.2,
) -> AudioComparison:
    """Compare two rendered audio streams with a monotonic DTW alignment.

    ``audio_f1`` is computed over speech windows so that pause placement does
    not dominate content similarity. ``audio_f1_all`` includes silence windows
    and is reported as a pacing diagnostic.
    """

    reference = extract_features(reference_pcm)
    output = extract_features(output_pcm)
    if band is None:
        band = max(60, abs(reference.descriptors.shape[0] - output.descriptors.shape[0]) + 30)
    matches = dtw_symmetric(
        reference.descriptors,
        output.descriptors,
        reference_speech=reference.speech,
        output_speech=output.speech,
        speech_penalty=speech_penalty,
        band=band,
    )
    reference_scores = np.zeros(reference.descriptors.shape[0], dtype=np.float32)
    output_scores = np.zeros(output.descriptors.shape[0], dtype=np.float32)
    similarities: list[float] = []
    for reference_index, output_index in matches:
        similarity = float(
            np.clip(
                reference.descriptors[reference_index]
                @ output.descriptors[output_index],
                -1.0,
                1.0,
            )
        )
        reference_scores[reference_index] = similarity
        output_scores[output_index] = similarity
        similarities.append(similarity)
    coverage_reference_all = float(np.mean(reference_scores >= tau))
    coverage_output_all = float(np.mean(output_scores >= tau))
    reference_speech = reference.speech >= speech_threshold
    output_speech = output.speech >= speech_threshold
    coverage_reference = (
        float(np.mean(reference_scores[reference_speech] >= tau))
        if bool(reference_speech.any())
        else coverage_reference_all
    )
    coverage_output = (
        float(np.mean(output_scores[output_speech] >= tau))
        if bool(output_speech.any())
        else coverage_output_all
    )

    def f1(left: float, right: float) -> float:
        denominator = left + right
        return 2.0 * left * right / denominator if denominator > 0 else 0.0

    audio_f1 = f1(coverage_reference, coverage_output)
    audio_f1_all = f1(coverage_reference_all, coverage_output_all)
    values = np.asarray(similarities, dtype=np.float32)
    return AudioComparison(
        audio_f1=audio_f1,
        audio_f1_all=audio_f1_all,
        coverage_reference=coverage_reference,
        coverage_output=coverage_output,
        coverage_reference_all=coverage_reference_all,
        coverage_output_all=coverage_output_all,
        mean_similarity=float(values.mean()) if values.size else 0.0,
        median_similarity=float(np.median(values)) if values.size else 0.0,
        p10_similarity=float(np.percentile(values, 10)) if values.size else 0.0,
        matched_windows=len(matches),
        reference_windows=int(reference.descriptors.shape[0]),
        output_windows=int(output.descriptors.shape[0]),
        matched_seconds=len(matches) * reference.window_hop_seconds,
        reference_seconds=reference.duration,
        output_seconds=output.duration,
    )


def interval_union(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Merge overlapping or touching intervals."""

    ordered = sorted((max(0.0, start), max(0.0, end)) for start, end in intervals)
    merged: list[tuple[float, float]] = []
    for start, end in ordered:
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def interval_duration(intervals: list[tuple[float, float]]) -> float:
    return sum(end - start for start, end in interval_union(intervals))


def interval_overlap(
    left: list[tuple[float, float]],
    right: list[tuple[float, float]],
) -> float:
    """Return the total intersection duration of two interval sets."""

    a = interval_union(left)
    b = interval_union(right)
    total = 0.0
    first = second = 0
    while first < len(a) and second < len(b):
        start = max(a[first][0], b[second][0])
        end = min(a[first][1], b[second][1])
        if end > start:
            total += end - start
        if a[first][1] < b[second][1]:
            first += 1
        else:
            second += 1
    return total


def interval_f1(
    reference: list[tuple[float, float]],
    output: list[tuple[float, float]],
    *,
    tolerance: float = 0.15,
) -> dict[str, float]:
    """Time-weighted precision/recall/F1 with a boundary tolerance."""

    reference_intervals = interval_union(reference)
    output_intervals = interval_union(output)
    reference_duration = interval_duration(reference_intervals)
    output_duration = interval_duration(output_intervals)
    if reference_duration <= 0 or output_duration <= 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "tolerance": tolerance}
    dilated_output = [(start - tolerance, end + tolerance) for start, end in output_intervals]
    dilated_reference = [
        (start - tolerance, end + tolerance) for start, end in reference_intervals
    ]
    covered_reference = interval_overlap(reference_intervals, dilated_output)
    covered_output = interval_overlap(output_intervals, dilated_reference)
    recall = min(1.0, covered_reference / reference_duration)
    precision = min(1.0, covered_output / output_duration)
    denominator = precision + recall
    f1 = 2.0 * precision * recall / denominator if denominator > 0 else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tolerance": tolerance,
    }


def silence_spans(
    pcm: np.ndarray,
    *,
    sample_rate: int = SAMPLE_RATE,
    threshold_db: float = -35.0,
    min_ms: int = 100,
    frame_ms: int = 10,
) -> list[tuple[float, float]]:
    """Return silence runs in seconds using the same profile as the edit."""

    signal = np.asarray(pcm, dtype=np.float32)
    frame_length = max(1, round(sample_rate * frame_ms / 1000))
    rms = frame_rms(signal, frame_length=frame_length, hop=frame_length)
    if rms.size == 0:
        return []
    threshold = float(10 ** (threshold_db / 20.0))
    silent = rms <= threshold
    minimum = max(1, round(min_ms / frame_ms))
    spans: list[tuple[float, float]] = []
    start: int | None = None
    for index, value in enumerate(silent):
        if value and start is None:
            start = index
        elif not value and start is not None:
            if index - start >= minimum:
                spans.append(
                    (
                        start * frame_ms / 1000,
                        index * frame_ms / 1000,
                    )
                )
            start = None
    if start is not None and len(silent) - start >= minimum:
        spans.append((start * frame_ms / 1000, len(silent) * frame_ms / 1000))
    return spans


def silence_stats(spans: list[tuple[float, float]]) -> dict[str, float]:
    total = sum(end - start for start, end in spans)
    maximum = max((end - start for start, end in spans), default=0.0)
    return {
        "total_seconds": round(total, 3),
        "max_seconds": round(maximum, 3),
        "events": len(spans),
    }


def loudness_stats(path: Path) -> dict[str, float | None]:
    """Measure integrated loudness and true peak with FFmpeg loudnorm."""

    binary = find_binary("ffmpeg")
    if binary is None:
        return {"lufs": None, "true_peak": None, "lra": None}
    command = [
        binary,
        "-hide_banner",
        "-nostats",
        "-i",
        str(Path(path).expanduser()),
        "-map",
        "0:a:0",
        "-af",
        "loudnorm=print_format=json",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=900.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"lufs": None, "true_peak": None, "lra": None}
    text = result.stderr.decode("utf-8", errors="replace")
    start = text.rfind("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return {"lufs": None, "true_peak": None, "lra": None}
    try:
        import json

        payload = json.loads(text[start : end + 1])
    except ValueError:
        return {"lufs": None, "true_peak": None, "lra": None}

    def value(key: str) -> float | None:
        try:
            return float(payload[key])
        except (KeyError, TypeError, ValueError):
            return None

    return {
        "lufs": value("input_i"),
        "true_peak": value("input_tp"),
        "lra": value("input_lra"),
    }


def spectral_correlation(
    reference_pcm: np.ndarray,
    output_pcm: np.ndarray,
    *,
    sample_rate: int = SAMPLE_RATE,
    n_fft: int = 2048,
    hop: int = 1024,
) -> float:
    """Correlate long-term average spectra on a common frequency grid."""

    def average_spectrum(pcm: np.ndarray) -> np.ndarray:
        signal = np.asarray(pcm, dtype=np.float32)
        if signal.size < n_fft:
            signal = np.pad(signal, (0, n_fft - signal.size))
        frame_count = 1 + (signal.size - n_fft) // hop
        usable = signal[: (frame_count - 1) * hop + n_fft]
        frames = np.lib.stride_tricks.sliding_window_view(usable, n_fft)[::hop]
        window = _hann(n_fft)
        spectrum = np.fft.rfft(frames * window, axis=1)
        power = spectrum.real**2 + spectrum.imag**2
        return np.mean(power, axis=0)

    reference = average_spectrum(reference_pcm)
    output = average_spectrum(output_pcm)
    size = min(reference.size, output.size)
    reference = reference[:size]
    output = output[:size]
    reference = 10.0 * np.log10(np.maximum(reference, EPSILON))
    output = 10.0 * np.log10(np.maximum(output, EPSILON))
    if reference.size < 2:
        return 0.0
    reference -= reference.mean()
    output -= output.mean()
    denominator = float(np.linalg.norm(reference) * np.linalg.norm(output))
    if denominator <= 0:
        return 0.0
    return float(np.dot(reference, output) / denominator)


def reconstruct(
    pcm: np.ndarray,
    intervals: list[tuple[float, float]],
    *,
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    """Concatenate source PCM at the given source-time intervals."""

    chunks: list[np.ndarray] = []
    limit = pcm.size
    for start, end in interval_union(intervals):
        start_sample = max(0, min(limit, round(start * sample_rate)))
        end_sample = max(start_sample, min(limit, round(end * sample_rate)))
        if end_sample > start_sample:
            chunks.append(pcm[start_sample:end_sample])
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks)
