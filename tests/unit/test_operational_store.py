"""SQLite as the operational store for jobs, batches and migration."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from videoflow.application import database
from videoflow.application.jobs import JobManager
from videoflow.engine.batch import BatchManager


def fake_runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
    progress("probe", 5, "probe")
    progress("export", 80, "export")
    return {"ok": True, "artifacts": {}}


def wait_for(manager: JobManager, job_id: str, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    terminal = {"succeeded", "failed", "cancelled"}
    while time.time() < deadline:
        if manager.get(job_id).status in terminal:
            # The worker writes the operational database in its finally block;
            # wait for that write before a caller reloads from SQLite.
            while time.time() < deadline:
                stored = {
                    item["job_id"]: item for item in database.list_jobs()
                }
                if stored.get(job_id, {}).get("status") in terminal:
                    return
                time.sleep(0.01)
            return
        time.sleep(0.01)
    raise AssertionError("job did not finish")


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    return tmp_path


def started_job(home: Path, tmp_path: Path) -> dict[str, object]:
    manager = JobManager(fake_runner, store_dir=tmp_path / "jobs")
    job = manager.start(tmp_path / "source.mp4", tmp_path / "output")
    wait_for(manager, str(job.job_id))
    return manager.get(str(job.job_id)).to_dict()


def test_jobs_are_read_from_the_database_before_json(
    home: Path, tmp_path: Path
) -> None:
    payload = started_job(home, tmp_path)
    for path in (tmp_path / "jobs").glob("*.json"):
        path.unlink()

    reloaded = JobManager(fake_runner, store_dir=tmp_path / "jobs")

    assert reloaded.get(str(payload["job_id"])).status == "succeeded"


def test_interrupted_jobs_are_requeued_from_the_database(
    home: Path, tmp_path: Path
) -> None:
    payload = started_job(home, tmp_path)
    payload.update({"status": "running", "stage": "export", "progress": 40})
    database.upsert_job(str(payload["job_id"]), payload)

    reloaded = JobManager(fake_runner, store_dir=tmp_path / "jobs")
    wait_for(reloaded, str(payload["job_id"]))

    job = reloaded.get(str(payload["job_id"]))
    assert job.status == "succeeded"
    assert job.error is None
    assert job.progress == 100


def test_stale_json_does_not_override_the_database(
    home: Path, tmp_path: Path
) -> None:
    payload = started_job(home, tmp_path)
    stale = dict(payload, status="failed", error={"message": "stale"})
    (tmp_path / "jobs" / f"{payload['job_id']}.json").write_text(
        json.dumps(stale), encoding="utf-8"
    )

    reloaded = JobManager(fake_runner, store_dir=tmp_path / "jobs")

    job = reloaded.get(str(payload["job_id"]))
    assert job.status == "succeeded"
    assert job.error is None


def test_reading_the_store_does_not_create_the_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "missing"))

    assert database.list_jobs() == []
    assert database.list_batches() == []
    assert not (tmp_path / "missing").exists()


def test_batches_are_restored_from_the_database(
    home: Path, tmp_path: Path
) -> None:
    payload = {
        "batch_id": "11111111-1111-1111-1111-111111111111",
        "source_dir": str(tmp_path / "in"),
        "output_root": str(tmp_path / "out"),
        "status": "succeeded",
        "items": [],
        "created_at": "2026-01-01T00:00:00+00:00",
        "finished_at": "2026-01-01T00:01:00+00:00",
    }
    database.upsert_batch(str(payload["batch_id"]), payload)

    jobs = JobManager(fake_runner, store_dir=None)
    batches = BatchManager(jobs, store_dir=tmp_path / "batches")

    assert batches.get(str(payload["batch_id"])).status == "succeeded"


def test_migration_imports_json_and_stamps_the_schema(
    home: Path, tmp_path: Path
) -> None:
    payload = started_job(home, tmp_path)
    # Simulate a home whose job exists only as JSON (the pre-2.1 layout).
    with database.connect() as connection:
        connection.execute("DELETE FROM jobs")
        connection.commit()
    (tmp_path / "assets.json").write_text(
        json.dumps({"assets": [{"id": "asset-1", "name": "clip"}]}),
        encoding="utf-8",
    )

    result = database.migrate_home()

    assert result["schema_version"] == 2
    assert result["imported"]["jobs"] >= 1
    assert result["imported"]["assets"] == 1
    assert [job["job_id"] for job in database.list_jobs()] == [payload["job_id"]]
    assert [asset["id"] for asset in database.list_assets_db()] == ["asset-1"]


def test_migration_never_overwrites_newer_database_rows(
    home: Path, tmp_path: Path
) -> None:
    payload = started_job(home, tmp_path)
    stale = dict(payload, status="queued", message="stale json")
    (tmp_path / "jobs" / f"{payload['job_id']}.json").write_text(
        json.dumps(stale), encoding="utf-8"
    )

    result = database.migrate_home()

    assert result["imported"]["jobs"] == 0
    [row] = [job for job in database.list_jobs() if job["job_id"] == payload["job_id"]]
    assert row["status"] == "succeeded"


def test_schema_1x_home_migrates_to_2x(home: Path, tmp_path: Path) -> None:
    payload = started_job(home, tmp_path)
    with database.connect() as connection:
        connection.execute(
            "UPDATE meta SET value = '1' WHERE key = 'schema_version'"
        )
        connection.commit()

    result = database.migrate_home()

    assert result["schema_version"] == 2
    with database.connect() as connection:
        version = connection.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()[0]
    assert version == "2"
    [row] = [job for job in database.list_jobs() if job["job_id"] == payload["job_id"]]
    assert row["status"] == "succeeded"
    assert row["idempotency_key"] == ""
