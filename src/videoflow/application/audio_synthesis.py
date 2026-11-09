"""Procedural, copyright-free music and Foley synthesis."""

from __future__ import annotations

import math
import wave
from pathlib import Path
from typing import Any

import numpy as np

SAMPLE_RATE = 48_000


def _write_wav(path: Path, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return path


def _envelope(length: int, attack: float = 0.02, release: float = 0.2) -> np.ndarray:
    env = np.ones(length, dtype=np.float32)
    attack_n = max(1, int(length * attack))
    release_n = max(1, int(length * release))
    env[:attack_n] = np.linspace(0.0, 1.0, attack_n, dtype=np.float32)
    env[-release_n:] = np.linspace(1.0, 0.0, release_n, dtype=np.float32)
    return env


def _sine(frequency: float, duration: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    t = np.arange(int(duration * sample_rate), dtype=np.float32) / sample_rate
    return np.sin(2 * math.pi * frequency * t).astype(np.float32)


def _saw(frequency: float, duration: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    t = np.arange(int(duration * sample_rate), dtype=np.float32) / sample_rate
    return (2.0 * (t * frequency - np.floor(t * frequency + 0.5))).astype(np.float32)


def _note(
    frequency: float,
    duration: float,
    *,
    kind: str = "pad",
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    if kind == "bass":
        return _sine(frequency / 2, duration, sample_rate) * 0.55
    if kind == "pulse":
        return _saw(frequency, duration, sample_rate) * 0.18
    return (
        _sine(frequency, duration, sample_rate) * 0.32
        + _sine(frequency * 2, duration, sample_rate) * 0.08
    )


def _place(target: np.ndarray, source: np.ndarray, start: int) -> np.ndarray:
    end = min(len(target), start + len(source))
    if end <= start:
        return target
    target[start:end] += source[: end - start]
    return target


def compose_music(
    directory: Path,
    *,
    duration_sec: float,
    bpm: float = 90.0,
    root_midi: int = 45,
    seed: int = 7,
    sample_rate: int = SAMPLE_RATE,
    max_loop_seconds: float = 120.0,
) -> dict[str, object]:
    rng = np.random.default_rng(seed)
    requested = max(1.0, float(duration_sec))
    duration = min(requested, max(1.0, float(max_loop_seconds)))
    looped = duration < requested
    length = int(duration * sample_rate)
    beat = 60.0 / max(40.0, min(220.0, bpm))
    bar = beat * 4
    root_hz = 440.0 * 2 ** ((root_midi - 69) / 12)
    minor = [0, 3, 7, 10]
    progression = [0, -3, 4, -5]
    pad = np.zeros(length, dtype=np.float32)
    bass = np.zeros(length, dtype=np.float32)
    pulse = np.zeros(length, dtype=np.float32)
    noise = np.zeros(length, dtype=np.float32) * 0.0
    bar_index = 0
    cursor = 0.0
    while cursor < duration:
        chord_root = progression[bar_index % len(progression)]
        chord = [
            root_hz * 2 ** ((chord_root + interval) / 12) for interval in minor
        ]
        chord_len = min(bar, duration - cursor)
        for frequency in chord:
            pad = _place(
                pad,
                _note(frequency, chord_len, kind="pad", sample_rate=sample_rate) * _envelope(
                    int(chord_len * sample_rate), 0.08, 0.25
                ),
                int(cursor * sample_rate),
            )
        bass = _place(
            bass,
            _note(chord[0], min(bar, chord_len), kind="bass", sample_rate=sample_rate)
            * _envelope(int(min(bar, chord_len) * sample_rate), 0.02, 0.15),
            int(cursor * sample_rate),
        )
        for step in range(4):
            pulse_start = int((cursor + step * beat) * sample_rate)
            pulse = _place(
                pulse,
                _note(
                    chord[step % len(chord)] * 2,
                    beat * 0.7,
                    kind="pulse",
                    sample_rate=sample_rate,
                )
                * _envelope(int(beat * 0.7 * sample_rate), 0.01, 0.3),
                pulse_start,
            )
        cursor += bar
        bar_index += 1
    # Restrained noise bed for texture.
    noise = (rng.standard_normal(length).astype(np.float32) * 0.004)
    mix = pad * 0.55 + bass * 0.45 + pulse * 0.35 + noise
    fade = min(int(2.0 * sample_rate), length)
    if fade > 0:
        mix[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
        mix[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    peak = float(np.max(np.abs(mix))) or 1.0
    mix = mix / max(1.0, peak) * 0.8
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "mix": _write_wav(directory / "music-bed.wav", mix, sample_rate),
        "pad": _write_wav(directory / "stem-pad.wav", pad, sample_rate),
        "bass": _write_wav(directory / "stem-bass.wav", bass, sample_rate),
        "pulse": _write_wav(directory / "stem-pulse.wav", pulse, sample_rate),
    }
    return {
        "bpm": bpm,
        "duration_sec": duration,
        "requested_duration_sec": requested,
        "loop_seconds": duration if looped else 0.0,
        "sample_rate": sample_rate,
        "files": {key: str(value) for key, value in paths.items()},
    }


def _notch(samples: np.ndarray, frequency: float, sample_rate: int) -> np.ndarray:
    spectrum = np.fft.rfft(samples)
    freqs = np.fft.rfftfreq(len(samples), 1.0 / sample_rate)
    band = np.abs(freqs - frequency) <= 180.0
    spectrum[band] *= 0.63
    return np.fft.irfft(spectrum, n=len(samples)).astype(np.float32)


def _foley(kind: str, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    rng = np.random.default_rng(sum(ord(char) for char in kind) % (2**32))
    duration = 0.45 if kind in {"paper_turn", "whoosh"} else 0.18
    if kind == "riser":
        duration = 1.2
    length = int(duration * sample_rate)
    t = np.arange(length, dtype=np.float32) / sample_rate
    if kind == "keyboard_click":
        noise = rng.standard_normal(length).astype(np.float32)
        envelope = np.exp(-t * 45.0)
        samples = noise * envelope * 0.5
        return _notch(samples, 3500.0, sample_rate)
    if kind == "paper_turn":
        noise = rng.standard_normal(length).astype(np.float32)
        envelope = np.exp(-t * 7.0) * (1.0 - np.exp(-t * 40.0))
        return noise * envelope * 0.45
    if kind == "marker_underline":
        return (
            np.sin(2 * np.pi * 900 * t) * np.exp(-t * 18.0) * 0.28
        ).astype(np.float32)
    if kind == "riser":
        frequency = 180 + 700 * (t / max(0.01, duration)) ** 2
        phase = 2 * np.pi * np.cumsum(frequency) / sample_rate
        return (np.sin(phase) * (t / duration) * 0.25).astype(np.float32)
    if kind == "impact":
        return (
            np.sin(2 * np.pi * 70 * t) * np.exp(-t * 22.0) * 0.5
        ).astype(np.float32)
    # whoosh
    noise = rng.standard_normal(length).astype(np.float32)
    envelope = np.sin(np.pi * t / max(0.01, duration)) ** 2
    return noise * envelope * 0.3


def synthesize_foley(
    directory: Path,
    cues: list[dict[str, Any]],
    *,
    sample_rate: int = SAMPLE_RATE,
) -> dict[str, object]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[dict[str, Any]] = []
    for index, cue in enumerate(cues):
        kind = str(cue.get("kind") or "whoosh")
        samples = _foley(kind, sample_rate)
        path = _write_wav(directory / f"{index + 1:03d}-{kind}.wav", samples, sample_rate)
        written.append(
            {
                "path": str(path),
                "kind": kind,
                "start_sec": float(cue.get("start_sec") or 0.0),
                "gain": float(cue.get("gain") or 0.35),
            }
        )
    return {"cues": written, "count": len(written)}
