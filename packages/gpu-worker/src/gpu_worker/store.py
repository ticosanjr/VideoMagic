"""SQLite metadata for artifacts and jobs.

Connections are opened per operation so the HTTP thread and the single GPU worker thread can
share the database without ``check_same_thread`` hazards.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    size INTEGER NOT NULL,
    path TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    capability TEXT NOT NULL,
    status TEXT NOT NULL,
    params TEXT NOT NULL,
    inputs TEXT NOT NULL,
    shared_inputs TEXT NOT NULL,
    shared_outputs TEXT NOT NULL DEFAULT '[]',
    shared_artifacts TEXT NOT NULL DEFAULT '[]',
    shared_error TEXT,
    error TEXT,
    artifacts TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    started_at REAL,
    finished_at REAL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""

TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    id: str
    filename: str
    size: int
    path: Path


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
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class JobStore:
    """Thin, thread-safe SQLite store for worker state."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(_SCHEMA)
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
            }
            if "shared_outputs" not in columns:
                connection.execute(
                    "ALTER TABLE jobs ADD COLUMN shared_outputs TEXT NOT NULL DEFAULT '[]'"
                )
            if "shared_artifacts" not in columns:
                connection.execute(
                    "ALTER TABLE jobs ADD COLUMN shared_artifacts TEXT NOT NULL DEFAULT '[]'"
                )
            if "shared_error" not in columns:
                connection.execute(
                    "ALTER TABLE jobs ADD COLUMN shared_error TEXT"
                )

    # Artifacts -----------------------------------------------------------------

    def add_artifact(self, artifact: ArtifactRecord) -> ArtifactRecord:
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO artifacts (id, filename, size, path, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (artifact.id, artifact.filename, artifact.size, str(artifact.path), time.time()),
            )
        stored = self.get_artifact(artifact.id)
        return stored or artifact

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT id, filename, size, path FROM artifacts WHERE id = ?", (artifact_id,)
            ).fetchone()
        if row is None:
            return None
        return ArtifactRecord(
            id=row["id"], filename=row["filename"], size=row["size"], path=Path(row["path"])
        )

    # Jobs ----------------------------------------------------------------------

    def create_job(
        self,
        *,
        job_id: str,
        capability: str,
        params: dict[str, Any],
        inputs: Sequence[str],
        shared_inputs: Sequence[str],
        shared_outputs: Sequence[str] = (),
    ) -> JobRecord:
        created_at = time.time()
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO jobs (id, capability, status, params, inputs, shared_inputs, "
                "shared_outputs, error, artifacts, created_at) "
                "VALUES (?, ?, 'queued', ?, ?, ?, ?, NULL, '[]', ?)",
                (
                    job_id,
                    capability,
                    json.dumps(params, sort_keys=True),
                    json.dumps(list(inputs)),
                    json.dumps(list(shared_inputs)),
                    json.dumps(list(shared_outputs)),
                    created_at,
                ),
            )
        return JobRecord(
            id=job_id,
            capability=capability,
            status="queued",
            params=dict(params),
            inputs=list(inputs),
            shared_inputs=list(shared_inputs),
            shared_outputs=list(shared_outputs),
            created_at=created_at,
        )

    def list_jobs(self, *, limit: int = 25) -> list[JobRecord]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return [job for row in rows if (job := _row_to_job(row)) is not None]

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._lock, self._connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row)

    def mark_running(self, job_id: str) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                "UPDATE jobs SET status = 'running', started_at = ? "
                "WHERE id = ? AND status = 'queued'",
                (time.time(), job_id),
            )
            return cursor.rowcount > 0

    def finish_job(
        self,
        job_id: str,
        status: str,
        *,
        error: str | None = None,
        artifacts: Sequence[str] = (),
        shared_artifacts: Sequence[str] = (),
        shared_error: str | None = None,
    ) -> bool:
        if status not in TERMINAL_STATUSES:
            raise ValueError(f"invalid terminal status: {status}")
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                "UPDATE jobs SET status = ?, error = ?, artifacts = ?, "
                "shared_artifacts = ?, shared_error = ?, finished_at = ? WHERE id = ?",
                (
                    status,
                    error,
                    json.dumps(list(artifacts)),
                    json.dumps(list(shared_artifacts)),
                    shared_error,
                    time.time(),
                    job_id,
                ),
            )
            return cursor.rowcount > 0

    def delete_job(self, job_id: str) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            return cursor.rowcount > 0

    def queue_depth(self) -> int:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM jobs WHERE status = 'queued'"
            ).fetchone()
        return int(row["total"]) if row is not None else 0

    def fail_interrupted_jobs(self) -> int:
        """Mark queued/running rows failed after a worker restart."""

        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                "UPDATE jobs SET status = 'failed', error = ?, finished_at = ? "
                "WHERE status IN ('queued', 'running')",
                ("worker restarted before the job finished", time.time()),
            )
            return cursor.rowcount

    def cleanup_finished(self, max_age_sec: float) -> list[str]:
        """Delete finished jobs older than ``max_age_sec`` and return their ids."""

        cutoff = time.time() - max_age_sec
        placeholders = ", ".join("?" for _ in TERMINAL_STATUSES)
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                f"SELECT id FROM jobs WHERE status IN ({placeholders}) "
                "AND COALESCE(finished_at, created_at) < ?",
                (*sorted(TERMINAL_STATUSES), cutoff),
            ).fetchall()
            job_ids = [row["id"] for row in rows]
            if job_ids:
                id_placeholders = ", ".join("?" for _ in job_ids)
                connection.execute(f"DELETE FROM jobs WHERE id IN ({id_placeholders})", job_ids)
        return job_ids


def _row_to_job(row: sqlite3.Row | None) -> JobRecord | None:
    if row is None:
        return None
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
