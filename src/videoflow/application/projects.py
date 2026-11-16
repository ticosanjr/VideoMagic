"""Project registry, locking, and atomic project-state persistence."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application import database
from videoflow.domain.errors import ProjectStateError, StateNotReadyError
from videoflow.domain.migrations import migrate_project_state
from videoflow.domain.state import MediaInfo, ProjectState


class ProjectRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    name: str
    output: str
    primary_source: str = ""
    sources: list[str] = Field(default_factory=list)
    channel_id: str = ""
    created_at: str = Field(default_factory=lambda: _now())
    updated_at: str = Field(default_factory=lambda: _now())
    revision: int = 1

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _project_id(value: str | None = None) -> str:
    if value:
        return value
    return str(uuid.uuid4())


def _lock_path(output: Path) -> Path:
    return output / ".videoflow.lock"


@contextmanager
def project_lock(output: Path) -> Iterator[None]:
    """Serialize project writes across threads and processes."""

    output = Path(output).expanduser()
    output.mkdir(parents=True, exist_ok=True)
    with open(_lock_path(output), "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def state_path(record: ProjectRecord) -> Path:
    return Path(record.output).expanduser() / "project_state.json"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _load_record(project_id: str) -> dict[str, Any] | None:
    payload = database.get_project(project_id)
    return payload if isinstance(payload, dict) else None


def _save_record(record: ProjectRecord) -> ProjectRecord:
    record.updated_at = _now()
    database.upsert_project(record.project_id, record.to_dict())
    _write_json(Path(record.output) / "project.json", record.to_dict())
    return record


def get_project(project_id: str) -> ProjectRecord:
    payload = _load_record(project_id)
    if payload is None:
        raise ProjectStateError(f"Unknown project: {project_id}")
    return ProjectRecord.model_validate(payload)


def list_projects() -> list[ProjectRecord]:
    return [ProjectRecord.model_validate(item) for item in database.list_projects()]


def project_for_output(output: Path, *, name: str = "") -> ProjectRecord | None:
    for record in list_projects():
        with contextlib.suppress(OSError):
            if Path(record.output).expanduser().resolve() == Path(output).expanduser().resolve():
                return record
    path = Path(output).expanduser() / "project.json"
    if path.is_file():
        try:
            return ProjectRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return None


def _media_for_sources(
    source_paths: list[str],
    *,
    adapter: Any | None = None,
) -> tuple[dict[str, MediaInfo], str]:
    from videoflow.adapters.ffmpeg import FFmpegAdapter
    from videoflow.domain.paths import resolve_allowed
    from videoflow.runtime import allowed_roots

    renderer = adapter or FFmpegAdapter()
    sources: dict[str, MediaInfo] = {}
    for index, raw in enumerate(source_paths, start=1):
        path = resolve_allowed(Path(raw), allowed_roots())
        media = renderer.probe(path)
        source_id = f"src{index}"
        sources[source_id] = media
    primary = next(iter(sources), "")
    return sources, primary


def init_project(
    *,
    name: str = "",
    output: Path | str,
    sources: list[str] | None = None,
    project_id: str | None = None,
    channel_id: str = "",
    adapter: Any | None = None,
) -> tuple[ProjectRecord, ProjectState]:
    """Create or adopt a project at ``output``."""

    output_path = Path(output).expanduser()
    output_path.mkdir(parents=True, exist_ok=True)
    existing = project_for_output(output_path, name=name)
    if existing is not None:
        record = existing
        state = load_project_state(record)
        if channel_id and channel_id != record.channel_id:
            record = record.model_copy(update={"channel_id": channel_id})
            _save_record(record)
        if sources:
            new_sources, primary = _media_for_sources(sources, adapter=adapter)
            for source_id, media in new_sources.items():
                state.add_source(source_id, media)
            if primary:
                state.primary_source_id = primary
                state.media_info = state.sources[primary]
            state = save_project_state(record, state, bump_revision=False)
            record = _refresh_record(record, state)
        return record, state

    state_file = output_path / "project_state.json"
    state: ProjectState
    state_id = project_id
    if state_file.is_file():
        try:
            state = ProjectState.model_validate_json(state_file.read_text(encoding="utf-8"))
            state_id = str(state.project_id)
        except (OSError, ValueError):
            state = ProjectState(project_id=UUID(_project_id(project_id)))
    else:
        state = ProjectState(project_id=UUID(_project_id(project_id)))
    source_media: dict[str, MediaInfo] = {}
    primary = state.primary_source_id
    if sources:
        source_media, primary = _media_for_sources(sources, adapter=adapter)
        for source_id, media in source_media.items():
            state.add_source(source_id, media)
        state.primary_source_id = primary
        state.media_info = state.sources[primary]
    record = ProjectRecord(
        project_id=state_id or str(state.project_id),
        name=name or output_path.name,
        output=str(output_path),
        primary_source=_source_paths(state)[1],
        sources=_source_paths(state)[0],
        channel_id=channel_id,
        revision=state.revision,
    )
    _save_record(record)
    save_project_state(record, state, bump_revision=False)
    return record, state


def _source_paths(state: ProjectState) -> tuple[list[str], str]:
    paths = [media.source_path for media in state.sources.values()]
    primary_media = state.source_media()
    return paths, primary_media.source_path if primary_media is not None else ""


def _refresh_record(record: ProjectRecord, state: ProjectState) -> ProjectRecord:
    record.revision = state.revision
    record.sources, record.primary_source = _source_paths(state)
    return _save_record(record)


def load_project_state(record: ProjectRecord) -> ProjectState:
    path = state_path(record)
    if not path.is_file():
        raise StateNotReadyError("Project has no project_state.json yet")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ProjectState.model_validate(migrate_project_state(payload))
    except (OSError, ValueError) as exc:
        raise ProjectStateError(f"Could not read project state: {exc}") from exc


def save_project_state(
    record: ProjectRecord,
    state: ProjectState,
    *,
    expected_revision: int | None = None,
    bump_revision: bool = True,
) -> ProjectState:
    output = Path(record.output).expanduser()
    with project_lock(output):
        current = load_project_state(record) if state_path(record).is_file() else None
        if (
            expected_revision is not None
            and current is not None
            and current.revision != expected_revision
        ):
            raise ProjectStateError(
                f"Revision conflict: expected {expected_revision}, current {current.revision}"
            )
        if bump_revision:
            state = state.model_copy(update={"revision": state.revision + 1})
        _write_json(state_path(record), state.model_dump(mode="json"))
        paths, primary_path = _source_paths(state)
        updated = record.model_copy(
            update={
                "revision": state.revision,
                "sources": paths,
                "primary_source": primary_path,
                "updated_at": _now(),
            }
        )
        _save_record(updated)
        return state
