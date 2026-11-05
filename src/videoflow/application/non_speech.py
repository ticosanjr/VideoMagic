"""Conservative detection of short impulsive non-speech events.

Coughs, throat clears, and clicks are short high-energy bursts. A trained audio
tagger is the long-term answer; this detector is a safe bridge: it only removes
bursts that are outside every kept word (with a margin) and that look broadband
or noisy rather than voiced.
"""

from __future__ import annotations

import math
import wave
from collections.abc import Sequence
from pathlib import Path

import numpy as np


def load_pcm_mono(path: Path | None, *, sample_rate: int = 48_000) -> np.ndarray:
    if path is None or not Path(path).is_file():
        return np.zeros(0, dtype=np.float32)
    try:
        with wave.open(str(path), "rb") as handle:
            channels = max(1, handle.getnchannels())
            width = handle.getsampwidth()
            rate = handle.getframerate()
            data = handle.readframes(handle.getnframes())
    except (OSError, EOFError, wave.Error):
        return np.zeros(0, dtype=np.float32)
    if width != 2 or rate <= 0 or not data:
        return np.zeros(0, dtype=np.float32)
    samples = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if rate != sample_rate and samples.size:
        # The timeline stores source samples at the media rate. Resample only
        # for the detector; the returned spans are converted back by the caller.
        target = max(1, round(samples.size * sample_rate / rate))
        positions = np.linspace(0, samples.size - 1, target)
        samples = np.interp(positions, np.arange(samples.size), samples).astype(
            np.float32
        )
    return samples.astype(np.float32)


def _flatness(frame: np.ndarray) -> float:
    if frame.size < 16:
        return 0.0
    window = np.hanning(frame.size).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(frame * window)) ** 2
    spectrum = np.maximum(spectrum, 1e-12)
    geometric = math.exp(float(np.mean(np.log(spectrum))))
    arithmetic = float(np.mean(spectrum))
    return geometric / arithmetic if arithmetic > 0 else 0.0


def detect_impulsive_noise(
    pcm: np.ndarray,
    word_spans: Sequence[tuple[int, int]],
    *,
    sample_rate: int = 48_000,
    frame_ms: int = 10,
    min_ms: int = 40,
    max_ms: int = 600,
    margin_ms: int = 80,
    rms_threshold: float = 0.02,
    zcr_threshold: float = 0.18,
    flatness_threshold: float = 0.35,
) -> list[tuple[int, int]]:
    """Return source spans of isolated impulsive noise between words."""

    signal = np.asarray(pcm, dtype=np.float32)
    if signal.size == 0:
        return []
    frame_length = max(1, round(sample_rate * frame_ms / 1000))
    count = signal.size // frame_length
    if count == 0:
        return []
    frames = signal[: count * frame_length].reshape(count, frame_length)
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    signs = np.signbit(frames)
    zcr = np.mean(signs[:, 1:] != signs[:, :-1], axis=1)
    active = rms > rms_threshold
    minimum = max(1, round(min_ms / frame_ms))
    maximum = max(minimum, round(max_ms / frame_ms))
    margin = max(0, round(margin_ms * sample_rate / 1000))
    spans: list[tuple[int, int]] = []
    index = 0
    while index < count:
        if not active[index]:
            index += 1
            continue
        end = index + 1
        while end < count and active[end]:
            end += 1
        length = end - index
        if minimum <= length <= maximum:
            start_sample = index * frame_length
            end_sample = end * frame_length
            protected = any(
                start_sample < word_end + margin
                and end_sample > word_start - margin
                for word_start, word_end in word_spans
            )
            if not protected:
                middle = frames[(index + end) // 2]
                noisy = (
                    _flatness(middle) >= flatness_threshold
                    or float(np.max(zcr[index:end])) >= zcr_threshold
                )
                if noisy:
                    spans.append((start_sample, end_sample))
        index = end
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
