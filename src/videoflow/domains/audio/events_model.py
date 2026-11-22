"""Lightweight event model training and scoring."""

# ruff: noqa: F401,F403,F405
from __future__ import annotations

import json
import math
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from videoflow.application.non_speech import (
    _flatness,
    _harmonicity,
    candidate_bursts,
    detect_impulsive_noise,
)

from .events_ast import _mfcc, _resample

_N_MFCC = 13
_N_MELS = 26
FEATURE_NAMES = (
    "duration_ms",
    "rms_mean",
    "rms_peak",
    "zcr_mean",
    "zcr_peak",
    "flatness",
    "harmonicity",
    "centroid",
    "rolloff",
    "flux",
    "low_ratio",
    "onset",
) + tuple(f"mfcc_{index}" for index in range(2 * _N_MFCC))


def _frame_features(
    frame: np.ndarray,
    sample_rate: int,
) -> tuple[float, float, float, float, float]:
    if frame.size < 8:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    window = np.hanning(frame.size).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(frame * window)) ** 2
    total = float(np.sum(spectrum))
    if total <= 1e-12:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    frequencies = np.fft.rfftfreq(frame.size, d=1.0 / sample_rate)
    centroid = float(np.sum(frequencies * spectrum) / total)
    cumulative = np.cumsum(spectrum)
    rolloff_index = int(np.searchsorted(cumulative, 0.85 * cumulative[-1]))
    rolloff = float(frequencies[min(rolloff_index, frequencies.size - 1)])
    low = float(np.sum(spectrum[frequencies <= 500.0]) / total)
    return (
        centroid / max(1.0, sample_rate / 2),
        rolloff / max(1.0, sample_rate / 2),
        low,
        _flatness(frame),
        _harmonicity(frame, sample_rate),
    )


def span_features(
    pcm: np.ndarray,
    start: int,
    end: int,
    *,
    sample_rate: int = 48_000,
    frame_ms: int = 10,
) -> np.ndarray | None:
    signal = np.asarray(pcm, dtype=np.float32)
    start = max(0, start)
    end = min(signal.size, end)
    if end - start < max(8, sample_rate // 1000):
        return None
    segment = signal[start:end]
    frame_length = max(8, round(sample_rate * frame_ms / 1000))
    usable = (segment.size // frame_length) * frame_length
    if usable < frame_length:
        return None
    frames = segment[:usable].reshape(-1, frame_length)
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    signs = np.signbit(frames)
    zcr = np.mean(signs[:, 1:] != signs[:, :-1], axis=1)
    peak = int(np.argmax(rms))
    centroid, rolloff, low, flatness, harmonicity = _frame_features(
        frames[peak], sample_rate
    )
    flux = float(np.mean(np.abs(np.diff(rms)))) / max(1e-6, float(np.mean(rms)))
    onset = float(np.max(rms)) / max(1e-6, float(np.mean(rms)))
    duration = (end - start) / sample_rate * 1000
    mfcc = _mfcc(frames, sample_rate)
    return np.asarray(
        [
            duration,
            float(np.mean(rms)),
            float(np.max(rms)),
            float(np.mean(zcr)),
            float(np.max(zcr)),
            flatness,
            harmonicity,
            centroid,
            rolloff,
            flux,
            low,
            onset,
            *mfcc,
        ],
        dtype=np.float64,
    )


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -30.0, 30.0)))


@dataclass(frozen=True, slots=True)
class EventModel:
    feature_names: tuple[str, ...]
    mean: np.ndarray
    scale: np.ndarray
    weights: np.ndarray
    bias: float
    threshold: float = 0.5
    metrics: dict[str, Any] | None = None

    def score(self, features: np.ndarray) -> float:
        normalized = (features - self.mean) / self.scale
        return float(_sigmoid(np.asarray([normalized @ self.weights + self.bias]))[0])

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_names": list(self.feature_names),
            "mean": [float(value) for value in self.mean],
            "scale": [float(value) for value in self.scale],
            "weights": [float(value) for value in self.weights],
            "bias": float(self.bias),
            "threshold": float(self.threshold),
            "metrics": self.metrics or {},
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EventModel:
        names = tuple(str(item) for item in payload["feature_names"])
        if names != FEATURE_NAMES:
            raise ValueError("audio event model feature set does not match")
        return cls(
            feature_names=names,
            mean=np.asarray(payload["mean"], dtype=np.float64),
            scale=np.asarray(payload["scale"], dtype=np.float64),
            weights=np.asarray(payload["weights"], dtype=np.float64),
            bias=float(payload["bias"]),
            threshold=float(payload.get("threshold", 0.5)),
            metrics=dict(payload.get("metrics", {})),
        )


def default_model_path() -> Path:
    home = os.environ.get("VIDEOFLOW_HOME", "").strip()
    base = Path(home).expanduser() if home else Path.home() / ".videoflow"
    return base / "models" / "audio-events" / "model.json"


def load_model(path: Path | None = None) -> EventModel | None:
    target = path or default_model_path()
    if not target.is_file():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        model = EventModel.from_dict(payload)
        metrics = model.metrics or {}
        # A model trained on too few or noisy labels is worse than the
        # heuristic. Only use one that clears a minimum quality bar.
        if metrics.get("precision", 0.0) < 0.5 or metrics.get("recall", 0.0) < 0.5:
            return None
        return model
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_model(model: EventModel, path: Path | None = None) -> Path:
    target = path or default_model_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(model.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def train_model(
    features: np.ndarray,
    labels: np.ndarray,
    *,
    epochs: int = 900,
    learning_rate: float = 0.15,
    l2: float = 1e-3,
    threshold: float = 0.5,
) -> EventModel:
    if features.ndim != 2 or features.shape[1] != len(FEATURE_NAMES):
        raise ValueError("unexpected feature matrix")
    if features.shape[0] < 4:
        raise ValueError("not enough events to train")
    mean = features.mean(axis=0)
    scale = features.std(axis=0)
    scale[scale < 1e-9] = 1.0
    normalized = (features - mean) / scale
    weights = np.zeros(normalized.shape[1], dtype=np.float64)
    bias = 0.0
    positives = max(1, int(np.sum(labels == 1)))
    negatives = max(1, int(np.sum(labels == 0)))
    balance = np.where(labels == 1, negatives / positives, 1.0)
    for _ in range(epochs):
        predictions = _sigmoid(normalized @ weights + bias)
        error = (predictions - labels) * balance
        gradient = normalized.T @ error / len(labels) + l2 * weights
        weights -= learning_rate * gradient
        bias -= learning_rate * float(np.mean(error))
    predictions = _sigmoid(normalized @ weights + bias)
    predicted = (predictions >= threshold).astype(int)
    accuracy = float(np.mean(predicted == labels))
    true_positive = int(np.sum((predicted == 1) & (labels == 1)))
    false_positive = int(np.sum((predicted == 1) & (labels == 0)))
    false_negative = int(np.sum((predicted == 0) & (labels == 1)))
    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, true_positive + false_negative)
    return EventModel(
        feature_names=FEATURE_NAMES,
        mean=mean,
        scale=scale,
        weights=weights,
        bias=bias,
        threshold=threshold,
        metrics={
            "events": int(features.shape[0]),
            "positives": positives,
            "negatives": negatives,
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
        },
    )


def score_candidates(
    pcm: np.ndarray,
    candidates: Sequence[tuple[int, int]],
    model: EventModel,
    *,
    sample_rate: int = 48_000,
) -> list[tuple[int, int]]:
    kept: list[tuple[int, int]] = []
    for start, end in candidates:
        features = span_features(pcm, start, end, sample_rate=sample_rate)
        if features is None:
            continue
        if model.score(features) >= model.threshold:
            kept.append((start, end))
    return kept
