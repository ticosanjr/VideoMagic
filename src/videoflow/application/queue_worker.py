"""Run one claimed job, with a heartbeat thread that keeps the lease alive."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from videoflow.application.jobs import TERMINAL, JobManager, _job_from_dict
from videoflow.application.queue_claim import claim_next, heartbeat

DEFAULT_LEASE_SECONDS = 120


@dataclass
class WorkerResult:
    job: Any
    worker_id: str
    claimed: bool


def run_once(
    manager: JobManager,
    worker_id: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    timeout: float = 3600.0,
) -> Any | None:
    """Claim and run one queued job. Returns ``None`` when the queue is empty."""

    claim = claim_next(worker_id, lease_seconds=lease_seconds)
    if claim is None:
        return None
    job = _job_from_dict(claim.payload)
    job.lease_expires_at = claim.lease_expires_at
    job.lease_owner = worker_id
    with manager._lock:  # noqa: SLF001 - the manager owns the run loop
        manager._jobs[str(job.job_id)] = job  # noqa: SLF001
    stop = threading.Event()

    def beat() -> None:
        interval = max(1.0, lease_seconds / 3.0)
        while not stop.wait(interval):
            if job.status in TERMINAL:
                return
            heartbeat(
                str(job.job_id),
                worker_id,
                lease_seconds=lease_seconds,
            )

    thread = threading.Thread(
        target=beat, name=f"videoflow-heartbeat-{job.job_id}", daemon=True
    )
    thread.start()
    try:
        manager._launch(job)  # noqa: SLF001
        deadline = time.monotonic() + max(0.1, timeout)
        while job.status not in TERMINAL and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        stop.set()
    return job


def serve(
    manager: JobManager,
    worker_id: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    poll_seconds: float = 1.0,
) -> None:
    """Keep claiming work until interrupted."""

    while True:
        job = run_once(manager, worker_id, lease_seconds=lease_seconds)
        if job is None:
            time.sleep(max(0.1, poll_seconds))
