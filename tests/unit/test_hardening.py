"""Log rotation, scheduled backups, and fault injection."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.recipe_jobs import manager_with_runner, start_recipe
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
        manager = manager_with_runner(runner)
        job = start_recipe(manager, source, blocked / "out", {})
        for _ in range(300):
            if job.status in {"failed", "succeeded", "cancelled"}:
                break
            time.sleep(0.01)
        assert job.status == "failed"
        assert job.error is not None
    finally:
        os.chmod(blocked, 0o700)


def test_disk_full_fails_an_export_without_a_success_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import errno
    import time


    def runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        output.mkdir(parents=True, exist_ok=True)
        raise OSError(errno.ENOSPC, "No space left on device")

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    manager = manager_with_runner(runner)
    job = start_recipe(manager, source, tmp_path / "out", {})
    for _ in range(300):
        if job.status in {"failed", "succeeded", "cancelled"}:
            break
        time.sleep(0.01)

    assert job.status == "failed"
    assert job.error is not None
    assert "No space" in str(job.error)


def test_offline_provider_falls_back_to_the_next(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from videoflow.adapters.llm import FallbackLlm, OpenAICompatibleLlm

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    failing = OpenAICompatibleLlm(
        base_url="http://offline.invalid/v1",
        model="x",
        retries=0,
        transport=httpx.MockTransport(offline),
    )

    class Working:
        def complete_json(self, prompt: str, schema_name: str) -> dict[str, object]:
            return {"ok": True}

    assert FallbackLlm([failing, Working()]).complete_json("p", "s") == {"ok": True}


def test_missing_whisper_model_is_a_typed_error(tmp_path: Path) -> None:
    from videoflow.adapters.whisper import WhisperCliAdapter
    from videoflow.domain.errors import VideoFlowError

    adapter = WhisperCliAdapter(binary=tmp_path / "missing", model=tmp_path / "missing.bin")
    try:
        adapter.transcribe(tmp_path / "audio.wav", 16000)
    except VideoFlowError as exc:
        assert "does not exist" in str(exc).lower() or "not found" in str(exc).lower()
    else:  # pragma: no cover - the call must fail
        raise AssertionError("missing model must raise")


def test_service_log_rotation_keeps_two_generations(tmp_path: Path) -> None:
    from videoflow.application.service_definitions import rotate_service_log

    log = tmp_path / "service.log"
    for _ in range(3):
        log.write_bytes(b"x" * 200)
        assert rotate_service_log(log, max_bytes=100, keep=2)

    assert (tmp_path / "service.log.1").is_file()
    assert (tmp_path / "service.log.2").is_file()
    assert not (tmp_path / "service.log.3").exists()
