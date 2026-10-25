"""Local workspaces that group a source, an output folder, and recent runs."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from videoflow.domain.errors import FilesystemError, StateNotReadyError
from videoflow.runtime import portable_home


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    source: str = ""
    output: str = ""
    created_at: str
    updated_at: str
    last_job_id: str = ""


class ProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    source: str = ""
    output: str = ""


def projects_dir() -> Path:
    directory = portable_home() / "projects"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def project_path(project_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", project_id).strip("-")
    if not safe:
        raise StateNotReadyError("Invalid project id.")
    return projects_dir() / f"{safe}.json"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def list_projects() -> list[Project]:
    items: list[Project] = []
    for path in sorted(projects_dir().glob("*.json")):
        try:
            items.append(Project.model_validate_json(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    items.sort(key=lambda item: item.updated_at, reverse=True)
    return items


def get_project(project_id: str) -> Project:
    path = project_path(project_id)
    if not path.is_file():
        raise StateNotReadyError(f"Unknown project: {project_id}")
    try:
        return Project.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StateNotReadyError(f"Invalid project record: {exc}") from exc


def _write(project: Project) -> Project:
    path = project_path(project.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(project.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return project


def create_project(request: ProjectRequest) -> Project:
    now = _now()
    project = Project(
        id=f"project-{uuid4().hex[:10]}",
        name=request.name.strip(),
        source=request.source.strip(),
        output=request.output.strip(),
        created_at=now,
        updated_at=now,
    )
    return _write(project)


def update_project(project_id: str, request: ProjectRequest) -> Project:
    project = get_project(project_id)
    updated = project.model_copy(
        update={
            "name": request.name.strip(),
            "source": request.source.strip(),
            "output": request.output.strip(),
            "updated_at": _now(),
        }
    )
    return _write(updated)


def delete_project(project_id: str) -> None:
    path = project_path(project_id)
    if not path.is_file():
        raise StateNotReadyError(f"Unknown project: {project_id}")
    try:
        path.unlink()
    except OSError as exc:
        raise FilesystemError(str(exc)) from exc


def touch_run(project_id: str, job_id: str) -> None:
    try:
        project = get_project(project_id)
    except StateNotReadyError:
        return
    _write(
        project.model_copy(
            update={"last_job_id": str(job_id), "updated_at": _now()}
        )
    )
