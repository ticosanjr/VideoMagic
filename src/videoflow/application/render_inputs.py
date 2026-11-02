"""Filter and path inputs shared by preview and timeline renderers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_filters(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(item) for item in payload.get("filters", []) if str(item)]


def video_track_filters(job: Any) -> list[str]:
    from videoflow.application.timeline_meta import load_meta

    try:
        meta = load_meta(job.output)
    except Exception:
        return []
    state = meta.tracks.get("video")
    if state is None or state.solo or not state.muted:
        return []
    return ["drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill"]


def track_filters(job: Any) -> list[str]:
    from videoflow.application.timeline_meta import load_meta

    try:
        meta = load_meta(job.output)
    except Exception:
        return []
    state = meta.tracks.get("audio")
    if state is None or state.solo or not state.muted:
        return []
    return ["volume=0"]


def audio_filters(job: Any) -> list[str]:
    return read_filters(job.output / "audio" / "master-filters.json") + track_filters(job)


def video_filters(job: Any) -> list[str]:
    return read_filters(job.output / "color" / "filters.json") + video_track_filters(job)


def ass_path(job: Any) -> Path:
    return job.output / "titles.ass"


def render_inputs(job: Any) -> tuple[list[str], list[str], Path]:
    return audio_filters(job), video_filters(job), ass_path(job)
