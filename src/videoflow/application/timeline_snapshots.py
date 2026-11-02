"""Named timeline snapshots and the project-state files used by recipes."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from videoflow.domain.state import ProjectState
from videoflow.runtime import ensure_home

SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def timelines_dir() -> Path:
    directory = ensure_home() / "timelines"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _duration_sec(state: ProjectState) -> float:
    media = state.media_info
    if media is None:
        return 0.0
    fps = media.fps_num / max(1, media.fps_den)
    last = max(
        (clip.timeline_out_frame for clip in state.video_segments),
        default=0,
    )
    return round(last / max(0.001, fps), 3)


def _source_fingerprint(state: ProjectState) -> str:
    media = state.media_info
    if media is None:
        return ""
    path = Path(media.source_path).expanduser()
    try:
        stat = path.stat()
    except OSError:
        return str(path)
    return f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"


def _metadata(snapshot_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": snapshot_id,
        "name": str(payload.get("name") or snapshot_id),
        "created_at": str(payload.get("created_at") or ""),
        "revision": int(payload.get("revision") or 1),
        "duration_sec": float(payload.get("duration_sec") or 0.0),
        "source_path": str(payload.get("source_path") or ""),
        "source_fingerprint": str(payload.get("source_fingerprint") or ""),
        "path": str(timelines_dir() / f"{snapshot_id}.json"),
        "job_id": str(payload.get("job_id") or ""),
    }


def snapshot_path(snapshot_id: str) -> Path:
    if not SAFE_ID.fullmatch(snapshot_id):
        raise ValueError(f"Invalid snapshot id: {snapshot_id}")
    return timelines_dir() / f"{snapshot_id}.json"


def save_snapshot(
    state: ProjectState,
    *,
    name: str = "",
    job_id: str = "",
) -> dict[str, Any]:
    snapshot_id = uuid4().hex[:16]
    label = name.strip() or f"Timeline {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}"
    payload = {
        "ok": True,
        "id": snapshot_id,
        "name": label,
        "created_at": _now(),
        "revision": state.revision,
        "duration_sec": _duration_sec(state),
        "source_path": state.media_info.source_path if state.media_info else "",
        "source_fingerprint": _source_fingerprint(state),
        "job_id": job_id,
        "state": state.model_dump(mode="json"),
    }
    destination = snapshot_path(snapshot_id)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, destination)
    return _metadata(snapshot_id, payload)


def list_snapshots() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in timelines_dir().glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict) or "state" not in payload:
            continue
        entries.append(_metadata(path.stem, payload))
    entries.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return entries


def read_snapshot(snapshot_id: str) -> tuple[dict[str, Any], ProjectState]:
    path = snapshot_path(snapshot_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Timeline snapshot is not an object")
    state = ProjectState.model_validate(payload.get("state") or payload)
    return _metadata(snapshot_id, payload), state


def read_snapshot_file(path: Path) -> tuple[dict[str, Any], ProjectState]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Timeline file is not an object")
    state = ProjectState.model_validate(payload.get("state") or payload)
    snapshot_id = str(payload.get("id") or Path(path).stem)
    metadata = _metadata(snapshot_id, payload)
    metadata["path"] = str(Path(path))
    return metadata, state


def delete_snapshot(snapshot_id: str) -> bool:
    path = snapshot_path(snapshot_id)
    if not path.is_file():
        return False
    path.unlink(missing_ok=True)
    return True
