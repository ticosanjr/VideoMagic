"""Job records and SQLite row mapping for the worker store."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class JobRecord:
    id: str
    capability: str
    status: str
    params: dict[str, Any] = field(default_factory=dict)
    inputs: list[str] = field(default_factory=list)
    shared_inputs: list[str] = field(default_factory=list)
    shared_outputs: list[str] = field(default_factory=list)
    shared_artifacts: list[str] = field(default_factory=list)
    shared_error: str | None = None
    error: str | None = None
    artifacts: list[str] = field(default_factory=list)
    priority: int = 0
    progress: int = 0
    stage: str = "queued"
    created_at: float = 0.0
    started_at: float | None = None
    finished_at: float | None = None

    def summary(self) -> dict[str, Any]:
        """Compact projection for dashboards and health payloads."""
        return {
            "job_id": self.id,
            "capability": self.capability,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "artifact_count": len(self.artifacts),
            "priority": self.priority,
            "progress": self.progress,
            "stage": self.stage,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "capability": self.capability,
            "status": self.status,
            "params": self.params,
            "inputs": self.inputs,
            "shared_inputs": self.shared_inputs,
            "shared_outputs": self.shared_outputs,
            "shared_artifacts": self.shared_artifacts,
            "shared_error": self.shared_error,
            "error": self.error,
            "artifacts": self.artifacts,
            "priority": self.priority,
            "progress": self.progress,
            "stage": self.stage,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


def _row_to_job(row: sqlite3.Row | None) -> JobRecord | None:
    if row is None:
        return None
    columns = set(row.keys())
    return JobRecord(
        id=row["id"],
        capability=row["capability"],
        status=row["status"],
        params=_json_object(row["params"]),
        inputs=_json_list(row["inputs"]),
        shared_inputs=_json_list(row["shared_inputs"]),
        shared_outputs=_json_list(row["shared_outputs"]),
        shared_artifacts=_json_list(row["shared_artifacts"]),
        shared_error=row["shared_error"],
        error=row["error"],
        artifacts=_json_list(row["artifacts"]),
        priority=int(row["priority"]) if "priority" in columns else 0,
        progress=int(row["progress"]) if "progress" in columns else 0,
        stage=str(row["stage"] or "queued") if "stage" in columns else "queued",
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


def _json_list(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _json_object(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}
