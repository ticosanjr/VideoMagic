"""Small, dependency-free audio-event classifier.

The heuristic in ``non_speech`` is a safe fallback, but coughs and throat clears
vary too much for fixed thresholds. This module extracts a compact feature
vector per candidate burst, trains a logistic-regression model on weakly
labelled events, and scores candidates at runtime. The model is a JSON file, so
no ML framework is required.
"""

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

_N_MFCC = 13
_N_MELS = 26


def _mel_filterbank(sample_rate: int, size: int) -> np.ndarray:
    def hz_to_mel(value: float) -> float:
        return 2595.0 * math.log10(1.0 + value / 700.0)

    def mel_to_hz(value: float) -> float:
        return 700.0 * (10.0 ** (value / 2595.0) - 1.0)

    low = hz_to_mel(80.0)
    high = hz_to_mel(min(8000.0, sample_rate / 2))
    points = np.linspace(low, high, _N_MELS + 2)
    frequencies = np.fft.rfftfreq(size, d=1.0 / sample_rate)
    bank = np.zeros((_N_MELS, frequencies.size), dtype=np.float64)
    for index in range(_N_MELS):
        left, center, right = points[index : index + 3]
        left_hz, center_hz, right_hz = (
            mel_to_hz(left),
            mel_to_hz(center),
            mel_to_hz(right),
        )
        rising = (frequencies - left_hz) / max(1e-9, center_hz - left_hz)
        falling = (right_hz - frequencies) / max(1e-9, right_hz - center_hz)
        bank[index] = np.maximum(0.0, np.minimum(rising, falling))
    return bank


def _mfcc(frames: np.ndarray, sample_rate: int) -> np.ndarray:
    window = np.hanning(frames.shape[1]).astype(np.float64)
    spectrum = np.abs(np.fft.rfft(frames * window, axis=1)) ** 2
    bank = _mel_filterbank(sample_rate, frames.shape[1])
    energies = np.log(np.maximum(1e-12, spectrum @ bank.T))
    size = _N_MELS
    dct = np.zeros((_N_MFCC, size), dtype=np.float64)
    for index in range(_N_MFCC):
        scale = math.sqrt(1.0 / size) if index == 0 else math.sqrt(2.0 / size)
        dct[index] = scale * np.cos(
            math.pi * index * (np.arange(size) + 0.5) / size
        )
    coefficients = energies @ dct.T
    return np.concatenate([coefficients.mean(axis=0), coefficients.std(axis=0)])


NOISE_LABELS = {
    "Cough",
    "Throat clearing",
    "Sneeze",
    "Snort",
    "Gasp",
    "Wheeze",
    "Breathing",
    "Sniff",
    "Grunt",
    "Sigh",
}

_AST: tuple[object, object, list[int]] | None = None
_AST_PATH: Path | None = None


def ast_model_path() -> Path | None:
    raw = os.environ.get("VIDEOFLOW_AUDIO_TAGGER", "").strip()
    if raw:
        path = Path(raw).expanduser()
        return path if (path / "config.json").is_file() else None
    default = Path.home() / ".videoflow" / "models" / "audio-tagging" / "ast-audioset"
    return default if (default / "config.json").is_file() else None


def _load_ast() -> tuple[object, object, list[int]] | None:
    global _AST, _AST_PATH
    path = ast_model_path()
    if path is None:
        return None
    if _AST is not None and path == _AST_PATH:
        return _AST
    try:
        from transformers import ASTFeatureExtractor, ASTForAudioClassification

        extractor = ASTFeatureExtractor.from_pretrained(str(path))
        model = ASTForAudioClassification.from_pretrained(str(path))
        model.eval()
        labels = [
            str(model.config.id2label[index])
            for index in range(len(model.config.id2label))
        ]
        noise = [index for index, label in enumerate(labels) if label in NOISE_LABELS]
        if not noise:
            return None
        _AST = (extractor, model, noise)
        _AST_PATH = path
        return _AST
    except Exception:
        _AST = None
        _AST_PATH = None
        return None


def _resample(clip: np.ndarray, source: int, target: int = 16_000) -> np.ndarray:
    if source == target or clip.size == 0:
        return clip.astype(np.float32)
    length = max(1, round(clip.size * target / source))
    positions = np.linspace(0, clip.size - 1, length)
    return np.interp(positions, np.arange(clip.size), clip).astype(np.float32)


def score_ast_candidates(
    pcm: np.ndarray,
    candidates: Sequence[tuple[int, int]],
    *,
    sample_rate: int = 48_000,
    threshold: float = 0.1,
    window_seconds: float = 1.0,
    batch_size: int = 8,
) -> list[tuple[int, int]]:
    """Keep candidates that AST tags as cough, throat clear, or similar."""

    loaded = _load_ast()
    if loaded is None or not candidates:
        return []
    import torch

    extractor, model, noise = loaded
    window = int(16_000 * window_seconds)
    signal = np.asarray(pcm, dtype=np.float32)
    kept: list[tuple[int, int]] = []
    for offset in range(0, len(candidates), batch_size):
        batch_candidates = candidates[offset : offset + batch_size]
        clips: list[np.ndarray] = []
        for start, end in batch_candidates:
            center = (start + end) // 2
            half = window // 2
            left = max(0, center - half)
            right = min(signal.size, center + half)
            clip = _resample(signal[left:right], sample_rate)
            clip = (
                np.pad(clip, (0, window - clip.size))
                if clip.size < window
                else clip[:window]
            )
            clips.append(clip)
        inputs = extractor(clips, sampling_rate=16_000, return_tensors="pt")
        with torch.no_grad():
            logits = model(**inputs).logits
        probabilities = torch.sigmoid(logits).numpy()
        scores = probabilities[:, noise].max(axis=1)
        for candidate, score in zip(batch_candidates, scores, strict=False):
            if float(score) >= threshold:
                kept.append(candidate)
    return kept


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


def detect_audio_events(
    pcm: np.ndarray,
    word_spans: Sequence[tuple[int, int]],
    *,
    sample_rate: int = 48_000,
    model: EventModel | None = None,
    frame_ms: int = 10,
    min_ms: int = 40,
    max_ms: int = 600,
    margin_ms: int = 80,
    rms_threshold: float = 0.02,
    use_ast: bool = False,
    ast_threshold: float = 0.1,
) -> list[tuple[int, int]]:
    """Detect non-speech events with AST, the trained model, or the heuristic."""

    heuristic = detect_impulsive_noise(
        pcm,
        word_spans,
        sample_rate=sample_rate,
        frame_ms=frame_ms,
        min_ms=min_ms,
        max_ms=max_ms,
        margin_ms=margin_ms,
        rms_threshold=rms_threshold,
    )
    if use_ast:
        candidates = candidate_bursts(
            pcm,
            word_spans,
            sample_rate=sample_rate,
            frame_ms=frame_ms,
            min_ms=min_ms,
            max_ms=max_ms,
            margin_ms=margin_ms,
            rms_threshold=rms_threshold,
        )
        ast = score_ast_candidates(
            pcm,
            candidates,
            sample_rate=sample_rate,
            threshold=ast_threshold,
        )
        if ast:
            heuristic = sorted({*heuristic, *ast})
    if model is None:
        return heuristic
    candidates = candidate_bursts(
        pcm,
        word_spans,
        sample_rate=sample_rate,
        frame_ms=frame_ms,
        min_ms=min_ms,
        max_ms=max_ms,
        margin_ms=margin_ms,
        rms_threshold=rms_threshold,
    )
    scored = score_candidates(pcm, candidates, model, sample_rate=sample_rate)
    return sorted({*heuristic, *scored})
