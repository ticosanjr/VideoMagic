"""Audio similarity and alignment helpers for cut calibration."""

# ruff: noqa: E402,F401,F403,F405
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


from .compare_dsp import *  # noqa: F401,F403
from .compare_dtw import *  # noqa: F401,F403
from .compare_dtw import _cost_matrix, _median_filter
from .compare_metrics import *  # noqa: F401,F403


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
