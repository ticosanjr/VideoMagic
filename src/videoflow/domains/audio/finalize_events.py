"""Discovery and validation of Foley cues for the final audio bed."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .finalize_result import AudioFinalizeError

SFX_PLAN_FILES = ("beat_map.json", "audio/beatmap.json", "audio/sfx-plan.json")


def resolve_project_path(root: Path, raw: Any) -> Path:
    path = Path(str(raw or "")).expanduser()
    if not path.is_absolute():
        path = root / path
    return path


def entry_gain_db(entry: dict[str, Any]) -> float:
    if entry.get("gain_db") is not None:
        try:
            return float(entry.get("gain_db") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    try:
        linear = float(entry.get("gain") or 0.0)
    except (TypeError, ValueError):
        linear = 0.0
    if linear <= 0:
        return 0.0
    return 20.0 * math.log10(max(0.0001, linear))


def entry_start_sec(entry: dict[str, Any], *, fps: float) -> float:
    if entry.get("start_sec") is not None:
        raw = entry.get("start_sec")
    elif "start_frame" in entry:
        raw = float(entry.get("start_frame") or 0.0) / max(1.0, float(fps))
    else:
        raw = 0.0
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 0.0


def discover_sfx_events(root: Path | str, *, fps: float = 30.0) -> list[dict[str, Any]]:
    """Read SFX cues from ``beat_map.json`` and ``audio/sfx-plan.json``."""

    project = Path(root).expanduser()
    events: list[dict[str, Any]] = []
    for relative in SFX_PLAN_FILES:
        payload_path = project / relative
        if not payload_path.is_file():
            continue
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        entries = (
            payload.get("sfx_events")
            or payload.get("sfx")
            or payload.get("cues")
            or []
        )
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            raw = str(entry.get("path") or "").strip()
            if not raw:
                continue
            events.append(
                {
                    "path": str(resolve_project_path(project, raw)),
                    "start_sec": entry_start_sec(entry, fps=fps),
                    "gain_db": entry_gain_db(entry),
                }
            )
    return events


def normalize_events(
    explicit: list[dict[str, Any]],
    discovered: list[dict[str, Any]],
    *,
    root: Path,
    fps: float = 30.0,
) -> list[dict[str, Any]]:
    """Merge explicit and autodetected cues without duplicating a cue."""

    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()
    for event in [*explicit, *discovered]:
        path = resolve_project_path(root, event.get("path"))
        start = entry_start_sec(event, fps=fps)
        key = (str(path), round(start, 6))
        if key in seen:
            continue
        seen.add(key)
        merged.append(
            {
                **event,
                "path": str(path),
                "start_sec": start,
                "gain_db": entry_gain_db(event),
            }
        )
    return merged


def prepare_sfx_events(
    root: Path,
    *,
    explicit: list[dict[str, Any]],
    duration: float,
    fps: float,
) -> tuple[list[dict[str, Any]], list[str], int]:
    """Return playable cues, warnings, and the deduplicated request count."""

    warnings: list[str] = []
    requested = normalize_events(
        explicit,
        discover_sfx_events(root, fps=fps),
        root=root,
        fps=fps,
    )
    valid: list[dict[str, Any]] = []
    for event in requested:
        path = resolve_project_path(root, event.get("path"))
        if not path.is_file():
            warnings.append(f"SFX event is missing and was skipped: {path}")
            continue
        start = entry_start_sec(event, fps=fps)
        if start > max(0.0, duration - 0.001):
            clamped = max(0.0, duration - 0.05)
            warnings.append(
                f"SFX event at {start:.3f}s exceeds the {duration:.3f}s timeline "
                f"and was clamped to {clamped:.3f}s: {path.name}"
            )
            start = clamped
        valid.append({**event, "path": str(path), "start_sec": start})
    if requested and not valid:
        raise AudioFinalizeError("No SFX events could be mixed; check the event paths.")
    return valid, warnings, len(requested)


__all__ = [
    "discover_sfx_events",
    "entry_gain_db",
    "entry_start_sec",
    "normalize_events",
    "prepare_sfx_events",
    "resolve_project_path",
]
