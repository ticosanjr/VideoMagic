from __future__ import annotations

import multiprocessing
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from tests.recipe_jobs import MINIMAL_RECIPE, manager_with_runner
from videoflow.application import database, queue_claim


def _payload(job_id: str) -> dict[str, object]:
    return {
        "job_id": job_id,
        "status": "queued",
        "priority": 0,
        "attempts": 0,
        "next_run": "",
        "source": "/tmp/source.mp4",
        "output": f"/tmp/{job_id}",
        "options": {"mode": "recipe", "recipe": MINIMAL_RECIPE},
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def _claim_worker(home: str, worker: str, output: multiprocessing.Queue) -> None:
    os.environ["VIDEOWFLOW_HOME"] = home
    claim = queue_claim.claim_next(worker, lease_seconds=60)
    output.put((worker, claim.job_id if claim else ""))


def test_two_processes_claim_different_jobs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    database.migrate_home()
    for index in range(2):
        database.upsert_job(f"job-{index}", _payload(f"job-{index}"))

    context = multiprocessing.get_context("spawn")
    results: multiprocessing.Queue = context.Queue()
    processes = [
        context.Process(target=_claim_worker, args=(str(tmp_path), f"w{i}", results))
        for i in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0
    claims = sorted(results.get(timeout=5) for _ in processes)
    assert {job for _, job in claims} == {"job-0", "job-1"}
    assert queue_claim.claim_next("late") is None


def test_expired_lease_is_recovered_and_heartbeat_checks_owner(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    database.migrate_home()
    database.upsert_job("job-a", _payload("job-a"))
    moment = datetime(2026, 1, 1, tzinfo=UTC)
    claim = queue_claim.claim_next("worker-a", lease_seconds=30, now=moment)
    assert claim is not None
    assert claim.payload["lease_owner"] == "worker-a"

    assert queue_claim.heartbeat("job-a", "other", now=moment) is False
    assert queue_claim.heartbeat("job-a", "worker-a", lease_seconds=300, now=moment) is True
    assert queue_claim.recover_expired(now=moment) == []

    later = datetime(2026, 1, 1, 0, 10, tzinfo=UTC)
    assert queue_claim.recover_expired(now=later) == ["job-a"]
    again = queue_claim.claim_next("worker-b", now=later)
    assert again is not None
    assert again.job_id == "job-a"


def test_worker_runs_a_claimed_job_and_updates_the_store(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application.queue_worker import run_once

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    database.migrate_home()
    job_id = str(uuid4())

    def runner(source, output, **kwargs):
        Path(output).mkdir(parents=True, exist_ok=True)
        kwargs["progress"]("done", 100, "done")
        return {"ok": True, "artifacts": {}}

    manager = manager_with_runner(runner=runner, store_dir=tmp_path / "jobs", load_store=False)
    database.upsert_job(job_id, _payload(job_id))
    job = run_once(manager, "worker-1", timeout=10)
    assert job is not None
    assert job.status == "succeeded", job.error
    stored = {item["job_id"]: item for item in database.list_jobs()}
    assert stored[job_id]["status"] == "succeeded"
    assert run_once(manager, "worker-2", timeout=1) is None
