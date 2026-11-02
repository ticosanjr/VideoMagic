"""Backup, restore, metrics, and query edges for the operational store."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from videoflow.application import database


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    return tmp_path


def _job(job_id: str = "job-1", status: str = "succeeded") -> dict[str, object]:
    return {
        "job_id": job_id,
        "status": status,
        "source": "/media/source.mp4",
        "output": "/media/out",
        "options": {"recipe_id": "podcast"},
        "priority": 2,
        "attempts": 1,
        "progress": 100,
        "next_run": "",
        "lease_expires_at": "",
        "created_at": "2026-01-01T00:00:00+00:00",
        "started_at": "2026-01-01T00:00:01+00:00",
        "finished_at": "2026-01-01T00:01:00+00:00",
    }


def _write_zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as bundle:
        for name, payload in entries.items():
            bundle.writestr(name, payload)
    return path


def test_backup_bundles_the_database_and_settings(home: Path) -> None:
    database.upsert_job("job-1", _job())
    (home / "settings.json").write_text('{"theme": "dark"}', encoding="utf-8")
    (home / "providers.json").write_text("[]", encoding="utf-8")
    destination = home / "backups" / "snapshot.zip"

    result = database.backup(destination)

    assert result == destination
    with zipfile.ZipFile(destination) as bundle:
        assert set(bundle.namelist()) == {
            "videoflow.db",
            "settings.json",
            "providers.json",
        }
        assert bundle.read("settings.json") == b'{"theme": "dark"}'
    assert not destination.with_suffix(".db").exists()


def test_backup_without_a_database_writes_an_empty_bundle(home: Path) -> None:
    destination = home / "backups" / "empty.zip"

    database.backup(destination)

    assert zipfile.is_zipfile(destination)
    with zipfile.ZipFile(destination) as bundle:
        assert bundle.namelist() == []


def test_restore_round_trips_database_and_files(home: Path) -> None:
    database.upsert_job("job-1", _job())
    (home / "settings.json").write_text('{"theme": "dark"}', encoding="utf-8")
    archive = database.backup(home / "snapshot.zip")
    database.db_path().unlink()
    for suffix in ("-wal", "-shm"):
        Path(str(database.db_path()) + suffix).write_bytes(b"stale")
    (home / "settings.json").write_text('{"theme": "light"}', encoding="utf-8")

    result = database.restore(archive)

    assert database.list_jobs()[0]["job_id"] == "job-1"
    assert json.loads((home / "settings.json").read_text(encoding="utf-8")) == {
        "theme": "dark"
    }
    assert set(result["restored"]) == {"videoflow.db", "settings.json"}
    assert not Path(str(database.db_path()) + "-wal").exists()
    assert not Path(str(database.db_path()) + "-shm").exists()


def test_restore_rejects_a_missing_backup(home: Path) -> None:
    with pytest.raises(ValueError, match="Backup not found"):
        database.restore(home / "missing.zip")


def test_restore_rejects_unknown_entries(home: Path) -> None:
    archive = _write_zip(home / "bad.zip", {"payload.exe": b"binary"})

    with pytest.raises(ValueError, match="Unexpected backup entries"):
        database.restore(archive)


def test_restore_rejects_invalid_json_settings(home: Path) -> None:
    archive = _write_zip(home / "bad.zip", {"settings.json": b"{"})

    with pytest.raises(ValueError):
        database.restore(archive)


def test_restore_rejects_an_unreadable_database(home: Path) -> None:
    archive = _write_zip(home / "bad.zip", {"videoflow.db": b"not a database"})

    with pytest.raises(ValueError, match="unreadable"):
        database.restore(archive)
    assert not (home / "restore.tmp.db").exists()


def test_restore_rejects_a_database_that_fails_integrity(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _write_zip(home / "bad.zip", {"videoflow.db": b"x"})

    class FakeConnection:
        def execute(self, statement: str) -> FakeConnection:
            return self

        def fetchone(self) -> tuple[str]:
            return ("corrupt",)

        def close(self) -> None:
            return None

    monkeypatch.setattr(database.sqlite3, "connect", lambda *_args, **_kwargs: FakeConnection())

    with pytest.raises(ValueError, match="integrity failed"):
        database.restore(archive)


def test_integrity_and_metrics_count_the_store(home: Path) -> None:
    database.upsert_job("job-1", _job())
    database.upsert_job("job-2", _job("job-2", "queued"))
    database.upsert_asset("asset-1", {"id": "asset-1", "name": "clip"})
    database.upsert_batch("batch-1", {"batch_id": "batch-1"})

    info = database.integrity()
    summary = database.metrics()

    assert info["ok"] is True
    assert info["jobs"] == 2
    assert info["assets"] == 1
    assert info["batches"] == 1
    assert summary["total_jobs"] == 2
    assert summary["jobs"] == {"succeeded": 1, "queued": 1}
    assert int(summary["home_bytes"]) > 0
    assert int(summary["disk_free"]) > 0


def test_integrity_reports_an_unavailable_store(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail() -> None:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(database, "connect", fail)

    result = database.integrity()

    assert result["ok"] is False
    assert result["integrity"] == "unavailable"
    assert "disk I/O error" in str(result["error"])


def test_corrupt_payload_rows_are_skipped(home: Path) -> None:
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO jobs (job_id, payload, updated_at) "
            "VALUES ('bad', 'not json', 'now')"
        )
        connection.execute(
            "INSERT INTO assets VALUES ('bad', 'not json', 'now')"
        )
        connection.execute(
            "INSERT INTO batches VALUES ('bad', 'not json', 'now')"
        )
        connection.commit()

    assert database.list_jobs() == []
    assert database.list_assets_db() == []
    assert database.list_batches() == []


def test_asset_queries_filter_kind_text_and_page(home: Path) -> None:
    database.upsert_asset("a1", {"id": "a1", "name": "Interview", "kind": "video"})
    database.upsert_asset("a2", {"id": "a2", "name": "Interview", "kind": "audio"})
    database.upsert_asset("a3", {"id": "a3", "name": "B-roll", "kind": "video"})

    assert {item["id"] for item in database.list_assets_db(kind="video")} == {
        "a1",
        "a3",
    }
    assert {item["id"] for item in database.list_assets_db(query="interview")} == {
        "a1",
        "a2",
    }
    assert len(database.list_assets_db(limit=1, offset=1)) == 1
    assert len(database.list_assets_db(limit=0)) == 1


def test_upserts_swallow_sqlite_errors(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail() -> None:
        raise sqlite3.OperationalError("locked")

    monkeypatch.setattr(database, "connect", fail)

    database.upsert_job("job-1", _job())
    database.upsert_asset("asset-1", {"id": "asset-1"})
    database.upsert_batch("batch-1", {"batch_id": "batch-1"})


def test_legacy_tables_gain_the_new_columns(home: Path, tmp_path: Path) -> None:
    path = database.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = sqlite3.connect(path)
    legacy.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY, payload TEXT)")
    legacy.commit()
    legacy.close()

    with database.connect() as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
        }
        version = connection.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()[0]

    assert {"status", "priority", "lease_expires", "finished_at"} <= columns
    assert version == "1"


def test_schema_is_initialized_once_per_database(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    original = database._create_schema

    def counted(connection: sqlite3.Connection) -> None:
        calls.append(1)
        original(connection)

    monkeypatch.setattr(database, "_create_schema", counted)

    with database.connect():
        pass
    with database.connect():
        pass

    assert len(calls) == 1


def test_assets_are_batched_in_one_transaction(home: Path) -> None:
    database.upsert_assets(
        [
            ("a1", {"id": "a1", "name": "one", "kind": "video"}),
            ("a2", {"id": "a2", "name": "two", "kind": "audio"}),
        ]
    )

    stored = database.list_assets_db()

    assert {item["id"] for item in stored} == {"a1", "a2"}


def test_database_errors_are_reported(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> None:
        raise sqlite3.OperationalError("disk is full")

    monkeypatch.setattr(database, "connect", broken)

    database.upsert_job("job-1", _job())

    assert "disk is full" in database.last_error()
