"""Filesystem contract for a VideoFlow workspace.

Layout for a project::

    <workspace>/projects/<project_id>/
        project.json
        script/
        assets/{voice,broll,images,sfx,music,graphics}/
        captions/
        renders/{drafts,final,manifests}/

All project-relative paths are resolved through :func:`resolve_within`, which
rejects absolute paths and traversal outside of the project directory.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

WORKSPACE_VERSION = 1
PROJECT_METADATA = "project.json"
STATE_FILE = "state.json"

ASSET_KINDS: tuple[str, ...] = (
    "voice",
    "broll",
    "images",
    "sfx",
    "music",
    "graphics",
)
RENDER_VARIANTS: tuple[str, ...] = ("drafts", "final", "manifests")

_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def validate_project_id(project_id: str) -> str:
    """Return ``project_id`` when it is a safe identifier, else raise ValueError."""

    if not isinstance(project_id, str) or not _PROJECT_ID_RE.fullmatch(project_id):
        raise ValueError(f"invalid project id: {project_id!r}")
    if project_id in {".", ".."}:
        raise ValueError(f"invalid project id: {project_id!r}")
    return project_id


def _validate_name(value: str, field: str) -> str:
    if not isinstance(value, str) or not _SAFE_NAME_RE.fullmatch(value):
        raise ValueError(f"invalid {field}: {value!r}")
    return value


def workspace_root() -> Path:
    """Return the workspace root.

    ``VF_WORKSPACE_ROOT`` wins when set; otherwise ``~/.videoflow/workspace``
    is used. The path is expanded but not created.
    """

    env_value = os.environ.get("VF_WORKSPACE_ROOT", "").strip()
    if env_value:
        return Path(env_value).expanduser()
    videoflow_home = os.environ.get("VIDEOWFLOW_HOME", "").strip()
    if videoflow_home:
        return Path(videoflow_home).expanduser() / "workspace"
    return Path.home() / ".videoflow" / "workspace"


def project_dir(project_id: str) -> Path:
    """Return the directory for ``project_id`` without creating it.

    ``VF_WORKSPACE_ROOT`` has historically been pointed either at the workspace
    parent or directly at its ``projects`` directory. Accept both forms so callers
    never produce ``projects/projects/{id}``.
    """

    root = workspace_root()
    if root.name == "projects":
        return root / validate_project_id(project_id)
    return root / "projects" / validate_project_id(project_id)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def read_project(project_id: str) -> dict[str, Any]:
    """Read ``project.json`` for a project."""

    path = project_dir(project_id) / PROJECT_METADATA
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"project metadata not found: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"invalid project metadata: {path}")
    return payload


def write_project(project_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Atomically write project metadata and return the normalized record."""

    project_id = validate_project_id(project_id)
    if not isinstance(payload, Mapping):
        raise TypeError("project metadata must be a mapping")

    folder = project_dir(project_id)
    existing: dict[str, Any] = {}
    try:
        existing = read_project(project_id)
    except (FileNotFoundError, ValueError):
        existing = {}

    record: dict[str, Any] = dict(payload)
    record["workspace_version"] = int(record.get("workspace_version", WORKSPACE_VERSION))
    record["project_id"] = project_id
    record["created_at"] = str(record.get("created_at") or existing.get("created_at") or _utc_now())
    record["updated_at"] = _utc_now()
    record.setdefault("sources", existing.get("sources") or [])
    record.setdefault("name", existing.get("name") or "")
    record.setdefault("channel_id", existing.get("channel_id") or "")
    record.setdefault("output", existing.get("output") or "")
    record.setdefault("state_path", str(folder / STATE_FILE))

    _atomic_write_json(folder / PROJECT_METADATA, record)
    return record


def ensure_project(
    project_id: str,
    name: str = "",
    output: str = "",
    channel_id: str = "",
) -> dict[str, Any]:
    """Create the project directory tree and project metadata if missing.

    Existing metadata is preserved for fields the caller does not provide, so
    repeated calls are safe and update ``updated_at`` only.
    """

    project_id = validate_project_id(project_id)
    root = project_dir(project_id)

    existing: dict[str, Any] = {}
    try:
        existing = read_project(project_id)
    except (FileNotFoundError, ValueError):
        existing = {}

    for relative in (
        "script",
        *(f"assets/{kind}" for kind in ASSET_KINDS),
        "captions",
        *(f"renders/{variant}" for variant in RENDER_VARIANTS),
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)

    record: dict[str, Any] = {
        "workspace_version": WORKSPACE_VERSION,
        "project_id": project_id,
        "name": name or str(existing.get("name") or ""),
        "channel_id": channel_id or str(existing.get("channel_id") or ""),
        "output": output or str(existing.get("output") or ""),
        "sources": list(existing.get("sources") or []),
        "state_path": str(root / STATE_FILE),
        "created_at": str(existing.get("created_at") or _utc_now()),
        "updated_at": _utc_now(),
    }
    _atomic_write_json(root / PROJECT_METADATA, record)
    return record


def resolve_within(project_id: str, relative_path: str | Path) -> Path:
    """Resolve a project-relative path, rejecting escapes from the project root."""

    root = project_dir(project_id).resolve()
    relative = Path(relative_path)
    if relative.is_absolute():
        raise ValueError(f"path must be relative to the project: {relative_path!r}")

    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"path escapes the project directory: {relative_path!r}")
    return candidate


def project_state_path(project_id: str) -> Path:
    """Return the persisted project state path."""

    return project_dir(project_id) / STATE_FILE


def asset_dir(project_id: str, kind: str) -> Path:
    """Return ``assets/<kind>`` for a project."""

    _validate_name(kind, "asset kind")
    return project_dir(project_id) / "assets" / kind


def render_dir(project_id: str, variant: str = "drafts") -> Path:
    """Return ``renders/<variant>`` for a project."""

    if variant not in RENDER_VARIANTS:
        raise ValueError(f"invalid render variant: {variant!r}")
    return project_dir(project_id) / "renders" / variant


def captions_dir(project_id: str) -> Path:
    """Return the captions directory for a project."""

    return project_dir(project_id) / "captions"
