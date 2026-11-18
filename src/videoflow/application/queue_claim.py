"""Atomic cross-process claim and lease recovery for the job queue."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from videoflow.application.clock import now_utc as _now
from videoflow.application.database import connect


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


@dataclass(frozen=True)
class Claim:
    job_id: str
    payload: dict[str, Any]
    worker_id: str
    lease_expires_at: str


def claim_next(
    worker_id: str,
    *,
    lease_seconds: int = 120,
    now: datetime | None = None,
) -> Claim | None:
    """Claim one queued job with a single atomic UPDATE.

    Two processes racing for the queue get different jobs or ``None``; the
    ``status = 'queued'`` predicate is what makes the update exclusive.
    """

    moment = now or _now()
    lease = _iso(moment + timedelta(seconds=max(1, lease_seconds)))
    connection = connect()
    try:
        connection.isolation_level = None
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT job_id, payload FROM jobs "
            "WHERE status IN ('queued', 'paused') AND cancel_requested = 0 "
            "AND (next_run IS NULL OR next_run = '' OR next_run <= ?) "
            "ORDER BY priority DESC, created_at ASC LIMIT 1",
            (_iso(moment),),
        ).fetchone()
        if row is None:
            connection.execute("COMMIT")
            return None
        job_id, raw = row
        payload = json.loads(raw)
        payload["status"] = "running"
        payload["lease_expires_at"] = lease
        payload["lease_owner"] = worker_id
        payload["attempts"] = int(payload.get("attempts") or 0) + 1
        payload["started_at"] = payload.get("started_at") or _iso(moment)
        updated = connection.execute(
            "UPDATE jobs SET status = 'running', attempts = ?, lease_expires = ?, "
            "payload = ?, updated_at = ? "
            "WHERE job_id = ? AND status IN ('queued', 'paused')",
            (
                payload["attempts"],
                lease,
                json.dumps(payload, sort_keys=True),
                _iso(moment),
                job_id,
            ),
        )
        if updated.rowcount != 1:
            connection.execute("ROLLBACK")
            return None
        connection.execute("COMMIT")
        return Claim(job_id, payload, worker_id, lease)
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def recover_expired(*, now: datetime | None = None) -> list[str]:
    """Return expired leases to the queue so another worker can pick them up."""

    moment = now or _now()
    connection = connect()
    recovered: list[str] = []
    try:
        connection.isolation_level = None
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            "SELECT job_id, payload FROM jobs WHERE status = 'running' "
            "AND lease_expires IS NOT NULL AND lease_expires != '' "
            "AND lease_expires <= ?",
            (_iso(moment),),
        ).fetchall()
        for job_id, raw in rows:
            payload = json.loads(raw)
            payload["status"] = "queued"
            payload["lease_expires_at"] = ""
            payload["lease_owner"] = ""
            payload["message"] = "Lease expired; requeued"
            connection.execute(
                "UPDATE jobs SET status = 'queued', lease_expires = '', payload = ?, "
                "updated_at = ? WHERE job_id = ? AND status = 'running'",
                (json.dumps(payload, sort_keys=True), _iso(moment), job_id),
            )
            recovered.append(job_id)
        connection.execute("COMMIT")
        return recovered
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def cancel_requested(job_id: str) -> bool:
    """Whether another process asked the shared store to cancel ``job_id``."""

    connection = connect()
    try:
        row = connection.execute(
            "SELECT cancel_requested FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    finally:
        connection.close()
    return bool(row and row[0])


def heartbeat(
    job_id: str, worker_id: str, *, lease_seconds: int = 120, now: datetime | None = None
) -> bool:
    """Extend a lease only when this worker still owns the job."""

    moment = now or _now()
    lease = _iso(moment + timedelta(seconds=max(1, lease_seconds)))
    connection = connect()
    try:
        row = connection.execute(
            "SELECT payload FROM jobs WHERE job_id = ? AND status = 'running'",
            (job_id,),
        ).fetchone()
        if row is None:
            return False
        payload = json.loads(row[0])
        if payload.get("lease_owner") != worker_id:
            return False
        payload["lease_expires_at"] = lease
        updated = connection.execute(
            "UPDATE jobs SET lease_expires = ?, payload = ?, updated_at = ? "
            "WHERE job_id = ? AND status = 'running'",
            (lease, json.dumps(payload, sort_keys=True), _iso(moment), job_id),
        )
        connection.commit()
        return updated.rowcount == 1
    finally:
        connection.close()
