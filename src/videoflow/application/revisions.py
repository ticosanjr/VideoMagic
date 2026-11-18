"""Incremental project snapshots used by timeline undo and restore."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from videoflow.application.clock import now_iso_ms
from videoflow.domain.errors import ProjectStateError
from videoflow.domain.state import ProjectState

HISTORY_DIR = "history"
MAX_SNAPSHOTS = 100
_REVISION_RE = re.compile(r"^rev_(\d{3,})$")


def history_dir(output: Path | str) -> Path:
    return Path(output).expanduser() / HISTORY_DIR


def _revision_path(output: Path | str, revision_id: str) -> Path:
    if not _REVISION_RE.fullmatch(revision_id):
        raise ProjectStateError(f"Invalid revision id: {revision_id}")
    return history_dir(output) / f"{revision_id}.json"


def _meta_path(output: Path | str, revision_id: str) -> Path:
    return history_dir(output) / f"{revision_id}.meta.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _next_revision(output: Path | str) -> str:
    highest = 0
    directory = history_dir(output)
    if directory.is_dir():
        for path in directory.glob("rev_*.json"):
            if path.name.endswith(".meta.json"):
                continue
            match = _REVISION_RE.fullmatch(path.stem)
            if match:
                highest = max(highest, int(match.group(1)))
    return f"rev_{highest + 1:03d}"


def create_snapshot(
    output: Path | str,
    state: ProjectState,
    *,
    reason: str = "",
    step: str = "",
) -> str:
    """Persist the current state as the next incremental revision.

    Callers that already hold the project lock should use this function
    directly. It never mutates ``state`` or the canonical document.
    """

    revision_id = _next_revision(output)
    directory = history_dir(output)
    directory.mkdir(parents=True, exist_ok=True)
    _write_json(
        _revision_path(output, revision_id),
        {
            "revision_id": revision_id,
            "state_revision": state.revision,
            "created_at": now_iso_ms(),
            "reason": reason,
            "step": step,
            "state": state.model_dump(mode="json"),
        },
    )
    _write_json(
        _meta_path(output, revision_id),
        {
            "revision_id": revision_id,
            "state_revision": state.revision,
            "created_at": now_iso_ms(),
            "reason": reason,
            "step": step,
            "segments": len(state.video_segments),
            "duration_frames": max(
                (clip.timeline_out_frame for clip in state.video_segments), default=0
            ),
        },
    )
    _prune(output)
    return revision_id


def _prune(output: Path | str) -> None:
    directory = history_dir(output)
    revisions: list[tuple[int, str]] = []
    if not directory.is_dir():
        return
    for path in directory.glob("rev_*.json"):
        if path.name.endswith(".meta.json"):
            continue
        match = _REVISION_RE.fullmatch(path.stem)
        if match:
            revisions.append((int(match.group(1)), path.stem))
    revisions.sort()
    for _number, revision_id in revisions[:-MAX_SNAPSHOTS]:
        _revision_path(output, revision_id).unlink(missing_ok=True)
        _meta_path(output, revision_id).unlink(missing_ok=True)


def list_snapshots(output: Path | str) -> list[dict[str, Any]]:
    directory = history_dir(output)
    if not directory.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob("rev_*.meta.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return sorted(items, key=lambda item: str(item.get("revision_id", "")), reverse=True)


def load_snapshot(output: Path | str, revision_id: str) -> ProjectState:
    path = _revision_path(output, revision_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        state_payload = payload.get("state") if isinstance(payload, dict) else None
        if not isinstance(state_payload, dict):
            raise ValueError("snapshot has no state")
        return ProjectState.model_validate(state_payload)
    except (OSError, ValueError) as exc:
        raise ProjectStateError(f"Could not read revision {revision_id}: {exc}") from exc


def latest_snapshot(output: Path | str) -> str:
    items = list_snapshots(output)
    if not items:
        raise ProjectStateError("Project has no saved revisions")
    return str(items[0]["revision_id"])


__all__ = [
    "HISTORY_DIR",
    "create_snapshot",
    "history_dir",
    "latest_snapshot",
    "list_snapshots",
    "load_snapshot",
]
