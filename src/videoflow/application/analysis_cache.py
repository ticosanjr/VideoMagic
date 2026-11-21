"""Content-addressed cache for scene and audio-energy analysis."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from videoflow.core.media_contract import PIPELINE_SCHEMA_VERSION
from videoflow.runtime import cache_root

CACHE_VERSION = PIPELINE_SCHEMA_VERSION


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def analysis_path(source: Path) -> Path:
    directory = cache_root() / "analysis"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{_sha256(source)}.json"


def _read(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def cached_scene_changes(source: Path) -> list[float]:
    from videoflow.application.video_analysis import detect_scene_changes

    path = analysis_path(source)
    payload = _read(path)
    if payload.get("version") == CACHE_VERSION and isinstance(payload.get("scene_times"), list):
        return [float(item) for item in payload["scene_times"]]
    times = detect_scene_changes(Path(source))
    payload.update({"version": CACHE_VERSION, "scene_times": times})
    _write(path, payload)
    return times


def cached_audio_energy(source: Path, sample_rate: int) -> list[tuple[int, int]]:
    from videoflow.application.audio_analysis import detect_audio_energy

    path = analysis_path(source)
    payload = _read(path)
    rate = max(1, int(sample_rate))
    peaks = payload.get("audio_peaks")
    if payload.get("version") == CACHE_VERSION and isinstance(peaks, list):
        result: list[tuple[int, int]] = []
        for item in peaks:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                result.append((round(float(item[0]) * rate), round(float(item[1]) * rate)))
        return result
    detected = detect_audio_energy(Path(source), rate)
    payload.update(
        {
            "version": CACHE_VERSION,
            "audio_peaks": [
                [round(start / rate, 6), round(end / rate, 6)] for start, end in detected
            ],
        }
    )
    _write(path, payload)
    return detected


__all__ = ["analysis_path", "cached_audio_energy", "cached_scene_changes"]
