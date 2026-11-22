"""YAMNet/AST-style audio event scoring."""


# ruff: noqa: E402
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

_N_MFCC = 13
_N_MELS = 26

from videoflow.application.non_speech import (
    _flatness,
    _harmonicity,
    candidate_bursts,
    detect_impulsive_noise,
)


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
