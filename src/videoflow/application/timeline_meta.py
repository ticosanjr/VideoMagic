"""Editorial timeline metadata: markers and track mute/solo/lock state."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.domain.errors import StateNotReadyError

META_FILE = "timeline_meta.json"


class Marker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=60)
    time_sec: float = Field(ge=0.0)
    label: str = Field(default="", max_length=300)
    color: str = Field(default="#38bdf8", max_length=20)


class TrackState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    muted: bool = False
    solo: bool = False
    locked: bool = False


class TimelineMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    markers: list[Marker] = Field(default_factory=list)
    tracks: dict[str, TrackState] = Field(default_factory=dict)


def meta_path(output: Path) -> Path:
    return Path(output) / META_FILE


def load_meta(output: Path) -> TimelineMeta:
    path = meta_path(output)
    if not path.is_file():
        return TimelineMeta()
    try:
        return TimelineMeta.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return TimelineMeta()


def save_meta(output: Path, meta: TimelineMeta) -> TimelineMeta:
    path = meta_path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(meta.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return meta


def add_marker(
    output: Path, *, marker_id: str, time_sec: float, label: str = "", color: str = "#38bdf8"
) -> TimelineMeta:
    if time_sec < 0:
        raise StateNotReadyError("Marker time must be non-negative.")
    meta = load_meta(output)
    meta.markers = [item for item in meta.markers if item.id != marker_id]
    meta.markers.append(
        Marker(id=marker_id, time_sec=time_sec, label=label, color=color)
    )
    meta.markers.sort(key=lambda item: item.time_sec)
    return save_meta(output, meta)


def remove_marker(output: Path, marker_id: str) -> TimelineMeta:
    meta = load_meta(output)
    meta.markers = [item for item in meta.markers if item.id != marker_id]
    return save_meta(output, meta)


def set_track(output: Path, track: str, state: TrackState) -> TimelineMeta:
    if track not in {"video", "audio", "captions", "broll"}:
        raise StateNotReadyError(f"Unknown track: {track}")
    meta = load_meta(output)
    meta.tracks[track] = state
    return save_meta(output, meta)
