"""Audio cross-correlation for dual-cam / facecam + screen synchronization."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.domain.errors import IngestError
from videoflow.domain.state import MediaInfo, ProjectState


def _read_pcm(path: Path, rate: int = 16000) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


def _normalize(signal: np.ndarray) -> np.ndarray:
    signal = signal - float(signal.mean())
    norm = float(np.linalg.norm(signal))
    return signal / norm if norm > 1e-9 else signal


def _lag(a: np.ndarray, b: np.ndarray) -> tuple[int, float]:
    """Return the lag of b relative to a and normalized confidence."""

    size = 1 << (len(a) + len(b) - 1).bit_length()
    correlation = np.fft.irfft(np.fft.rfft(a, size) * np.conj(np.fft.rfft(b, size)), size)
    index = int(np.argmax(correlation))
    if index > size // 2:
        index -= size
    peak = float(correlation[index])
    confidence = abs(peak) / max(1e-9, float(np.linalg.norm(a) * np.linalg.norm(b)))
    return index, min(1.0, confidence)


def _offset_ms(a: np.ndarray, b: np.ndarray, rate: int) -> tuple[float, float]:
    lag, confidence = _lag(a, b)
    return lag / rate * 1000.0, confidence


def sync_multicam(
    state: ProjectState,
    directory: Path,
    *,
    primary_source_id: str = "",
    secondary_source_id: str = "",
    apply: bool = False,
    min_confidence: float = 0.2,
    sample_rate: int = 16000,
) -> dict[str, object]:
    """Measure the audio offset between two project sources."""

    source_ids = list(state.sources)
    if len(source_ids) < 2:
        raise IngestError("Multicam sync needs at least two sources")
    primary = primary_source_id or state.primary_source_id or source_ids[0]
    secondary = secondary_source_id or next(item for item in source_ids if item != primary)
    if primary not in state.sources or secondary not in state.sources:
        raise IngestError("Multicam source id is not present in the project")
    primary_media: MediaInfo = state.sources[primary]
    secondary_media: MediaInfo = state.sources[secondary]
    directory = Path(directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    adapter = FFmpegAdapter()
    primary_pcm = adapter.extract_pcm(
        Path(primary_media.source_path),
        directory / "primary.wav",
        sample_rate=sample_rate,
    )
    secondary_pcm = adapter.extract_pcm(
        Path(secondary_media.source_path),
        directory / "secondary.wav",
        sample_rate=sample_rate,
    )
    a = _normalize(_read_pcm(primary_pcm))
    b = _normalize(_read_pcm(secondary_pcm))
    limit = sample_rate * 600
    a = a[:limit]
    b = b[:limit]
    offset, confidence = _offset_ms(a, b, sample_rate)
    windows = 4
    chunk = max(1, min(len(a), len(b)) // windows)
    offsets: list[float] = []
    for index in range(windows):
        start = index * chunk
        end = start + chunk
        if end > min(len(a), len(b)):
            break
        window_offset, _ = _offset_ms(a[start:end], b[start:end], sample_rate)
        offsets.append(window_offset)
    drift = (max(offsets) - min(offsets)) if len(offsets) >= 2 else 0.0
    applied = bool(apply and confidence >= min_confidence and abs(offset) <= 60_000)
    report = {
        "schema_version": 1,
        "primary_source_id": primary,
        "secondary_source_id": secondary,
        "offset_ms": round(offset, 3),
        "offset_frames": round(offset / 1000 * (primary_media.fps_num / primary_media.fps_den), 3),
        "drift_ms": round(drift, 3),
        "confidence": round(confidence, 4),
        "method": "gcc-phat/normalized-cross-correlation",
        "applied": applied,
        "min_confidence": min_confidence,
    }
    target = directory / "multicam_manifest.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    updated = state.model_copy(deep=True)
    if applied:
        updated.source_offsets[secondary] = int(round(offset / 1000 * sample_rate))
    return {"state": updated, "manifest": str(target), **report}
