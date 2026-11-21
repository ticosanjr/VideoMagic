"""Project registry, locking, and atomic project-state persistence."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field
from vf_shared.contracts.workspace import ensure_project, project_dir, write_project

from videoflow.application import database
from videoflow.application.state_sidecars import (
    load_state_from_index,
    write_state_index,
)
from videoflow.domain.errors import (
    ProjectStateError,
    StateNotReadyError,
    TimelineConflict,
)
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
    style_id: str = ""
    created_at: str = Field(default_factory=lambda: _now())
    updated_at: str = Field(default_factory=lambda: _now())
    revision: int = 1
    status: Literal["active", "archived"] = "active"
    archived_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def project_uuid(value: str | None = None) -> UUID:
    """Map a slug or UUID to the UUID stored inside ``ProjectState``."""

    if not value:
        return uuid.uuid4()
    try:
        return UUID(str(value))
    except ValueError:
        return uuid5(NAMESPACE_URL, f"videoflow:{value}")


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


def _sync_workspace(record: ProjectRecord, state: ProjectState) -> None:
    """Mirror canonical metadata and state into the shared workspace."""

    folder = project_dir(record.project_id)
    ensure_project(
        record.project_id,
        name=record.name,
        output=record.output,
        channel_id=record.channel_id,
    )
    paths, primary_path = _source_paths(state)
    write_project(
        record.project_id,
        {
            "project_id": record.project_id,
            "name": record.name,
            "output": record.output,
            "channel_id": record.channel_id,
            "style_id": record.style_id,
            "sources": paths,
            "primary_source": primary_path,
            "state_path": str(folder / "state.json"),
            "revision": state.revision,
            "schema_version": state.schema_version,
        },
    )
    _write_json(folder / "state.json", state.model_dump(mode="json"))


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
    style_id: str = "",
    adapter: Any | None = None,
) -> tuple[ProjectRecord, ProjectState]:
    """Create or adopt a project at ``output``."""

    output_path = Path(output).expanduser()
    output_path.mkdir(parents=True, exist_ok=True)
    existing = project_for_output(output_path, name=name)
    if existing is not None:
        record = existing
        state = load_project_state(record)
        updates: dict[str, Any] = {}
        if channel_id and channel_id != record.channel_id:
            updates["channel_id"] = channel_id
        if style_id and style_id != record.style_id:
            updates["style_id"] = style_id
        if updates:
            record = record.model_copy(update=updates)
            _save_record(record)
            if channel_id:
                from videoflow.application.brand_kit import brand_kit_root

                brand_kit_root(channel_id).mkdir(parents=True, exist_ok=True)
        if style_id and state.style_id != style_id:
            state = state.model_copy(update={"style_id": style_id})
            state = save_project_state(record, state, bump_revision=False)
            record = _refresh_record(record, state)
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
            with contextlib.suppress(OSError):
                state_file.replace(state_file.with_name(f"{state_file.name}.corrupt"))
            state = ProjectState(project_id=project_uuid(project_id))
    else:
        state = ProjectState(project_id=project_uuid(project_id))
    if style_id and state.style_id != style_id:
        state = state.model_copy(update={"style_id": style_id})
    source_media: dict[str, MediaInfo] = {}
    primary = state.primary_source_id
    if sources:
        source_media, primary = _media_for_sources(sources, adapter=adapter)
        for source_id, media in source_media.items():
            state.add_source(source_id, media)
        state.primary_source_id = primary
        state.media_info = state.sources[primary]
    record = ProjectRecord(
        project_id=project_id or state_id or str(state.project_id),
        name=name or output_path.name,
        output=str(output_path),
        primary_source=_source_paths(state)[1],
        sources=_source_paths(state)[0],
        channel_id=channel_id,
        style_id=style_id or state.style_id,
        revision=state.revision,
    )
    _save_record(record)
    if channel_id:
        from videoflow.application.brand_kit import brand_kit_root

        brand_kit_root(channel_id).mkdir(parents=True, exist_ok=True)
    save_project_state(record, state, bump_revision=False)
    return record, state


def _source_paths(state: ProjectState) -> tuple[list[str], str]:
    paths = [media.source_path for media in state.sources.values()]
    primary_media = state.source_media()
    return paths, primary_media.source_path if primary_media is not None else ""


def _refresh_record(record: ProjectRecord, state: ProjectState) -> ProjectRecord:
    record.revision = state.revision
    record.style_id = state.style_id or record.style_id
    record.sources, record.primary_source = _source_paths(state)
    return _save_record(record)


def load_project_state(record: ProjectRecord) -> ProjectState:
    path = state_path(record)
    if not path.is_file():
        workspace_state = project_dir(record.project_id) / "state.json"
        if workspace_state.is_file():
            path = workspace_state
        else:
            indexed = load_state_from_index(record.output)
            if indexed is not None:
                return indexed
            raise StateNotReadyError("Project has no project_state.json yet")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("sidecars"):
            indexed = load_state_from_index(record.output)
            if indexed is not None:
                return indexed
        return ProjectState.model_validate(migrate_project_state(payload))
    except (OSError, ValueError) as exc:
        indexed = load_state_from_index(record.output)
        if indexed is not None:
            return indexed
        raise ProjectStateError(f"Could not read project state: {exc}") from exc


def save_project_state(
    record: ProjectRecord,
    state: ProjectState,
    *,
    expected_revision: int | None = None,
    bump_revision: bool = True,
    snapshot: bool = False,
    snapshot_reason: str = "",
    snapshot_step: str = "",
    reset: bool = False,
) -> ProjectState:
    output = Path(record.output).expanduser()
    with project_lock(output):
        current = load_project_state(record) if state_path(record).is_file() else None
        if (
            expected_revision is not None
            and current is not None
            and current.revision != expected_revision
        ):
            if not reset:
                raise TimelineConflict(
                    "Revision conflict: expected "
                    f"{expected_revision}, current {current.revision}"
                )
            from videoflow.application.revisions import create_snapshot

            create_snapshot(
                output,
                current,
                reason=snapshot_reason or "before_reset",
                step=snapshot_step or "reset",
            )
        if snapshot and current is not None:
            from videoflow.application.revisions import create_snapshot

            create_snapshot(
                output,
                current,
                reason=snapshot_reason,
                step=snapshot_step,
            )
        if bump_revision:
            state = state.model_copy(update={"revision": state.revision + 1})
        _write_json(state_path(record), state.model_dump(mode="json"))
        write_state_index(output, state)
        _sync_workspace(record, state)
        paths, primary_path = _source_paths(state)
        updated = record.model_copy(
            update={
                "revision": state.revision,
                "style_id": state.style_id or record.style_id,
                "sources": paths,
                "primary_source": primary_path,
                "updated_at": _now(),
            }
        )
        _save_record(updated)
        return state


def project_disk_size(record: ProjectRecord) -> int:
    """Best-effort recursive size for lifecycle listings."""

    root = Path(record.output).expanduser()
    if not root.is_dir():
        return 0
    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            with contextlib.suppress(OSError):
                total += path.stat().st_size
    return total


def archive_project(record: ProjectRecord, *, archived: bool = True) -> ProjectRecord:
    status: Literal["active", "archived"] = "archived" if archived else "active"
    updated = record.model_copy(
        update={
            "status": status,
            "archived_at": _now() if archived else "",
            "updated_at": _now(),
        }
    )
    return _save_record(updated)


def delete_project(record: ProjectRecord, *, force: bool = False) -> dict[str, Any]:
    """Remove the project output and its registry/workspace entries."""

    root = Path(record.output).expanduser()
    if root.exists() and not force:
        raise ProjectStateError("Project output is not empty; pass force=true to delete it")
    if root == Path(root.anchor) or root == Path.home():
        raise ProjectStateError("Refusing to delete an unsafe project path")
    if root.exists():
        shutil.rmtree(root)
    database.delete_project(record.project_id)
    workspace = project_dir(record.project_id)
    if workspace.exists():
        shutil.rmtree(workspace)
    return {"project_id": record.project_id, "output": str(root), "deleted": True}


def clone_project(
    record: ProjectRecord,
    *,
    name: str = "",
    output: str = "",
    project_id: str = "",
) -> tuple[ProjectRecord, ProjectState]:
    """Clone decoded state without copying or re-analysing the source media."""

    source_state = load_project_state(record)
    target = Path(output).expanduser() if output else Path(record.output).expanduser()
    if not output:
        target = target.with_name(f"{target.name}-copy")
    if target.exists() and any(target.iterdir()):
        raise ProjectStateError(f"Clone output is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    project_id = project_id or str(uuid.uuid4())
    state = source_state.model_copy(
        update={
            "project_id": project_uuid(project_id),
            "revision": 1,
            "pipeline": source_state.pipeline.model_copy(
                update={
                    "run_id": "",
                    "step": "",
                    "checkpoints": [],
                }
            ),
        }
    )
    cloned = ProjectRecord(
        project_id=project_id,
        name=name or f"{record.name} (copy)",
        output=str(target),
        primary_source=record.primary_source,
        sources=list(record.sources),
        channel_id=record.channel_id,
        style_id=record.style_id,
        revision=1,
    )
    saved = save_project_state(cloned, state, bump_revision=False)
    return get_project(project_id), saved


__all__ = [
    "ProjectRecord",
    "archive_project",
    "clone_project",
    "delete_project",
    "get_project",
    "init_project",
    "list_projects",
    "load_project_state",
    "project_disk_size",
    "project_for_output",
    "project_lock",
    "project_uuid",
    "save_project_state",
    "state_path",
]
