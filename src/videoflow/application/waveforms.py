"""Cached RMS peaks for timeline audio clips.

Peaks are computed once per source file at 50 ms resolution and cached under
``<home>/waveforms``. A timeline range is a slice of that cache, resampled to
the number of bars the canvas needs, so scrolling and zooming never touch
FFmpeg.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import threading
import wave
from array import array
from pathlib import Path
from typing import Any

from videoflow.adapters.ffmpeg import FFmpegAdapter

BUCKET_SEC = 0.05
SAMPLE_RATE = 4000
MAX_BUCKETS = 200_000


def cache_dir() -> Path:
    from videoflow.runtime import portable_home

    return portable_home() / "waveforms"


def _digest(source: Path) -> str:
    stat = source.stat()
    payload = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{SAMPLE_RATE}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def cache_path(source: Path) -> Path:
    return cache_dir() / f"{_digest(source)}.json"


def _normalise(values: list[float]) -> list[float]:
    peak = max(values, default=0.0)
    if peak <= 0:
        return [0.0 for _ in values]
    return [round(min(1.0, value / peak), 4) for value in values]


def compute_peaks(wav_path: Path, *, bucket_samples: int = 200) -> list[float]:
    """Return normalised RMS peaks from a mono 16-bit PCM WAV."""

    with contextlib.closing(wave.open(str(wav_path), "rb")) as handle:
        if handle.getsampwidth() != 2:
            raise ValueError("Expected 16-bit PCM")
        peaks: list[float] = []
        remaining = bucket_samples
        total = 0.0
        count = 0
        while True:
            frame = handle.readframes(min(4096, remaining))
            if not frame:
                break
            samples = array("h")
            samples.frombytes(frame)
            for sample in samples:
                total += float(sample) * float(sample)
                count += 1
            remaining -= len(samples)
            if remaining <= 0:
                peaks.append((total / max(1, count)) ** 0.5)
                total = 0.0
                count = 0
                remaining = bucket_samples
        if count:
            peaks.append((total / max(1, count)) ** 0.5)
    return _normalise(peaks)


_locks_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def _source_lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


def _read_cache(path: Path) -> dict[str, Any] | None:
    cached = cache_path(path)
    if not cached.is_file():
        return None
    try:
        payload = json.loads(cached.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if payload.get("bucket_sec") == BUCKET_SEC and payload.get("peaks"):
        return payload
    return None


def analyse_source(source: Path, *, refresh: bool = False) -> dict[str, Any]:
    """Return ``{bucket_sec, duration_sec, peaks}`` for one media file."""

    path = Path(source).expanduser()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    if not refresh:
        cached = _read_cache(path)
        if cached is not None:
            return cached
    lock = _source_lock(path)
    with lock:
        if not refresh:
            cached = _read_cache(path)
            if cached is not None:
                return cached
        import tempfile

        with tempfile.TemporaryDirectory() as scratch:
            wav_path = Path(scratch) / "audio.wav"
            adapter = FFmpegAdapter()
            adapter.extract_pcm(path, wav_path, sample_rate=SAMPLE_RATE)
            peaks = compute_peaks(wav_path, bucket_samples=int(SAMPLE_RATE * BUCKET_SEC))
        cache = {
            "source": str(path),
            "bucket_sec": BUCKET_SEC,
            "duration_sec": round(len(peaks) * BUCKET_SEC, 3),
            "peaks": peaks[:MAX_BUCKETS],
        }
        try:
            target = cache_path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(cache), encoding="utf-8")
            temporary.replace(target)
        except OSError:
            pass
        return cache


def peaks_for_range(
    source: Path,
    *,
    start_sec: float,
    end_sec: float,
    buckets: int,
) -> dict[str, Any]:
    payload = analyse_source(source)
    peaks: list[float] = list(payload["peaks"])
    width = max(1, min(4096, int(buckets)))
    start = max(0, int(start_sec / BUCKET_SEC))
    end = min(len(peaks), max(start + 1, int(round(end_sec / BUCKET_SEC))))
    window = peaks[start:end] or [0.0]
    if len(window) == width:
        sampled = window
    else:
        sampled = []
        for index in range(width):
            left = int(index * len(window) / width)
            right = max(left + 1, int((index + 1) * len(window) / width))
            sampled.append(max(window[left:right]))
    return {
        "ok": True,
        "source": str(source),
        "bucket_sec": BUCKET_SEC,
        "start_sec": round(start_sec, 3),
        "end_sec": round(end_sec, 3),
        "peaks": [round(value, 4) for value in sampled],
    }
