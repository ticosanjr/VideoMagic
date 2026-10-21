"""Reusable flat job-configuration templates and config import/export."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from videoflow.domain.config import StrictModel
from videoflow.domain.errors import FilesystemError, StateNotReadyError
from videoflow.runtime import portable_home

_DISALLOWED = {
    "source",
    "output",
    "transcript",
    "transcript_state",
    "project_id",
    "revision",
    "modules_config",
    "module_enabled",
    "overrides",
}


class ProjectTemplate(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = ""
    options: dict[str, Any] = Field(default_factory=dict)


def templates_dir() -> Path:
    directory = portable_home() / "project_templates"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def sanitize_options(options: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in options.items() if key not in _DISALLOWED}


def list_templates() -> list[dict[str, object]]:
    templates: list[dict[str, object]] = []
    for path in sorted(templates_dir().glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            templates.append(payload)
        except (OSError, ValueError):
            continue
    return templates


def get_template(name: str) -> ProjectTemplate:
    path = _path(name)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise StateNotReadyError(f"Project template not found: {name}") from exc
    except ValueError as exc:
        raise FilesystemError(f"Project template is invalid: {exc}") from exc
    payload["name"] = name
    return ProjectTemplate.model_validate(payload)


def save_template(template: ProjectTemplate) -> dict[str, object]:
    clean = template.model_copy(update={"options": sanitize_options(template.options)})
    _path(clean.name).write_text(
        json.dumps(clean.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return clean.model_dump(mode="json")


def delete_template(name: str) -> None:
    path = _path(name)
    if not path.is_file():
        raise StateNotReadyError(f"Project template not found: {name}")
    path.unlink()


def export_config(options: dict[str, Any]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "options": sanitize_options(options),
    }


def import_config(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != 1:
        raise FilesystemError("Unsupported config schema version.")
    options = payload.get("options")
    if not isinstance(options, dict):
        raise FilesystemError("Config options must be an object.")
    return sanitize_options(options)


def _path(name: str) -> Path:
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", name.strip().casefold()).strip("-")
    if not cleaned:
        raise FilesystemError("Project template name is empty.")
    return templates_dir() / f"{cleaned}.json"
