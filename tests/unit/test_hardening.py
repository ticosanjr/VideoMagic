"""Log rotation, scheduled backups, and fault injection."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from videoflow.application import database
from videoflow.application.backups import prune_backups, scheduled_backup
from videoflow.application.services import rotate_log


def test_rotate_log_keeps_the_configured_generations(tmp_path: Path) -> None:
    log = tmp_path / "server.log"
    for _ in range(4):
        log.write_text("x" * 200, encoding="utf-8")
        assert rotate_log(log, max_bytes=100, keep=2)

    assert (tmp_path / "server.log.1").is_file()
    assert (tmp_path / "server.log.2").is_file()
    assert not (tmp_path / "server.log.3").exists()


def test_rotate_log_is_a_noop_below_the_limit(tmp_path: Path) -> None:
    log = tmp_path / "server.log"
    log.write_text("small", encoding="utf-8")
    assert rotate_log(log, max_bytes=1000) is False
    assert not (tmp_path / "server.log.1").exists()


def test_scheduled_backup_prunes_old_snapshots(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    directory = tmp_path / "backups"
    for index in range(4):
        (directory).mkdir(exist_ok=True)
        (directory / f"videoflow-2026010{index}-000000.zip").write_bytes(b"old")

    fresh = scheduled_backup(keep=2, directory=directory)

    remaining = sorted(path.name for path in directory.glob("videoflow-*.zip"))
    assert len(remaining) == 2
    assert fresh.name in remaining


def test_prune_backups_keeps_the_newest(tmp_path: Path) -> None:
    directory = tmp_path / "backups"
    directory.mkdir()
    for index in range(5):
        (directory / f"videoflow-2026010{index}-000000.zip").write_bytes(b"x")

    removed = prune_backups(keep=3, directory=directory)

    assert len(removed) == 2
    assert len(list(directory.glob("videoflow-*.zip"))) == 3


def test_corrupt_database_reads_as_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "videoflow.db").write_bytes(b"not a database")
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(home))

    assert database.list_jobs() == []


def test_migration_survives_a_corrupt_json_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    jobs = home / "jobs"
    jobs.mkdir(parents=True)
    (jobs / "broken.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(home))

    result = database.migrate_home()

    assert result["ok"] is True
    assert result["imported"]["jobs"] == 0


def test_job_fails_cleanly_when_the_output_is_not_writable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import time

    from videoflow.application.jobs import JobManager

    def runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        output.mkdir(parents=True, exist_ok=True)
        (output / "artifact.txt").write_text("x", encoding="utf-8")
        return {"ok": True, "artifacts": {}}

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    os.chmod(blocked, 0o500)
    try:
        manager = JobManager(runner)
        job = manager.start(source, blocked / "out", {})
        for _ in range(300):
            if job.status in {"failed", "succeeded", "cancelled"}:
                break
            time.sleep(0.01)
        assert job.status == "failed"
        assert job.error is not None
    finally:
        os.chmod(blocked, 0o700)


def test_api_timeline_rejects_a_corrupt_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from fastapi.testclient import TestClient

    from videoflow.api.app import create_app
    from videoflow.application.jobs import JobManager

    def runner(source: Path, output: Path, **kwargs):
        output.mkdir(parents=True, exist_ok=True)
        (output / "project_state.json").write_text("{broken", encoding="utf-8")
        return {"ok": True, "state_path": str(output / "project_state.json")}

    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    manager = JobManager(runner)
    client = TestClient(create_app(jobs=manager))
    job = manager.start(tmp_path / "source.mp4", tmp_path / "out", {})
    for _ in range(200):
        if job.status in {"succeeded", "failed"}:
            break
        import time

        time.sleep(0.01)

    response = client.get(f"/api/v1/jobs/{job.job_id}/timeline")

    assert response.status_code in {422, 500}
