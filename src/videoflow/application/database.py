"""SQLite operational index for jobs, assets, and backups."""

from __future__ import annotations

import contextlib
import json
import shutil
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from videoflow.runtime import portable_home

DB_FILE = "videoflow.db"


def db_path() -> Path:
    return portable_home() / DB_FILE


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10.0)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS jobs ("
        "job_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS assets ("
        "asset_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS batches ("
        "batch_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1')"
    )
    connection.commit()
    return connection


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def upsert_job(job_id: str, payload: dict[str, Any]) -> None:
    try:
        with contextlib.closing(connect()) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO jobs (job_id, payload, updated_at) VALUES (?, ?, ?)",
                (job_id, json.dumps(payload, sort_keys=True), _now()),
            )
            connection.commit()
    except sqlite3.Error:
        pass


def list_jobs() -> list[dict[str, Any]]:
    if not db_path().is_file():
        return []
    try:
        with contextlib.closing(connect()) as connection:
            rows = connection.execute(
                "SELECT payload FROM jobs ORDER BY updated_at"
            ).fetchall()
    except sqlite3.Error:
        return []
    result: list[dict[str, Any]] = []
    for (payload,) in rows:
        try:
            result.append(json.loads(payload))
        except ValueError:
            continue
    return result


def upsert_asset(asset_id: str, payload: dict[str, Any]) -> None:
    try:
        with contextlib.closing(connect()) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO assets (asset_id, payload, updated_at) VALUES (?, ?, ?)",
                (asset_id, json.dumps(payload, sort_keys=True), _now()),
            )
            connection.commit()
    except sqlite3.Error:
        pass


def list_assets_db() -> list[dict[str, Any]]:
    if not db_path().is_file():
        return []
    try:
        with contextlib.closing(connect()) as connection:
            rows = connection.execute(
                "SELECT payload FROM assets ORDER BY updated_at"
            ).fetchall()
    except sqlite3.Error:
        return []
    result: list[dict[str, Any]] = []
    for (payload,) in rows:
        try:
            result.append(json.loads(payload))
        except ValueError:
            continue
    return result


def list_batches() -> list[dict[str, Any]]:
    if not db_path().is_file():
        return []
    try:
        with contextlib.closing(connect()) as connection:
            rows = connection.execute(
                "SELECT payload FROM batches ORDER BY updated_at"
            ).fetchall()
    except sqlite3.Error:
        return []
    result: list[dict[str, Any]] = []
    for (payload,) in rows:
        try:
            result.append(json.loads(payload))
        except ValueError:
            continue
    return result


def upsert_batch(batch_id: str, payload: dict[str, Any]) -> None:
    try:
        with contextlib.closing(connect()) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO batches (batch_id, payload, updated_at) VALUES (?, ?, ?)",
                (batch_id, json.dumps(payload, sort_keys=True), _now()),
            )
            connection.commit()
    except sqlite3.Error:
        pass


def integrity() -> dict[str, object]:
    try:
        with contextlib.closing(connect()) as connection:
            value = connection.execute("PRAGMA integrity_check").fetchone()[0]
            jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            assets = connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
            batches = connection.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
        return {
            "ok": value == "ok",
            "integrity": value,
            "jobs": jobs,
            "assets": assets,
            "batches": batches,
        }
    except sqlite3.Error as exc:
        return {"ok": False, "integrity": "unavailable", "error": str(exc)}


def backup(destination: Path) -> Path:
    """Write a consistent ZIP snapshot of the local database and settings files."""

    destination = Path(destination).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(".db")
    source = db_path()
    if source.is_file():
        connection = connect()
        connection.commit()
        target = sqlite3.connect(temp)
        connection.backup(target)
        target.close()
        connection.close()
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as bundle:
        if temp.is_file():
            bundle.write(temp, "videoflow.db")
            temp.unlink(missing_ok=True)
        for name in ("settings.json", "providers.json", "models-local.json"):
            path = portable_home() / name
            if path.is_file():
                bundle.write(path, name)
    return destination


def metrics() -> dict[str, object]:
    info = integrity()
    jobs = list_jobs()
    counts: dict[str, int] = {}
    for job in jobs:
        status = str(job.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return {
        "ok": True,
        "database": info,
        "jobs": counts,
        "total_jobs": len(jobs),
        "home_bytes": sum(
            item.stat().st_size for item in portable_home().rglob("*") if item.is_file()
        ),
        "disk_free": shutil.disk_usage(portable_home()).free,
    }


def restore(source: Path) -> dict[str, object]:
    """Restore a backup ZIP produced by ``backup`` after validating it."""

    source = Path(source).expanduser()
    if not source.is_file():
        raise ValueError(f"Backup not found: {source}")
    allowed = {"videoflow.db", "settings.json", "providers.json", "models-local.json"}
    restored: list[str] = []
    with zipfile.ZipFile(source) as bundle:
        names = {item.filename for item in bundle.infolist()}
        unknown = names - allowed
        if unknown:
            raise ValueError(f"Unexpected backup entries: {', '.join(sorted(unknown))}")
        if "videoflow.db" in names:
            temp_db = portable_home() / "restore.tmp.db"
            temp_db.write_bytes(bundle.read("videoflow.db"))
            check = sqlite3.connect(temp_db)
            integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
            check.close()
            if integrity != "ok":
                temp_db.unlink(missing_ok=True)
                raise ValueError(f"Backup database integrity failed: {integrity}")
            for suffix in ("-wal", "-shm"):
                Path(str(db_path()) + suffix).unlink(missing_ok=True)
            shutil.copy2(temp_db, db_path())
            temp_db.unlink(missing_ok=True)
            restored.append("videoflow.db")
        for name in allowed - {"videoflow.db"}:
            if name not in names:
                continue
            payload = bundle.read(name)
            target = portable_home() / name
            if name.endswith(".json"):
                json.loads(payload.decode("utf-8"))
            target.write_text(payload.decode("utf-8"), encoding="utf-8")
            restored.append(name)
    return {"ok": True, "restored": restored}


def migrate_home() -> dict[str, object]:
    """Import existing JSON stores into SQLite and stamp the schema version."""

    imported = {"jobs": 0, "assets": 0, "batches": 0}
    jobs_dir = portable_home() / "jobs"
    if jobs_dir.is_dir():
        for path in jobs_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                upsert_job(str(payload.get("job_id") or path.stem), payload)
                imported["jobs"] += 1
            except (OSError, ValueError):
                continue
    asset_file = portable_home() / "assets.json"
    if asset_file.is_file() and not list_assets_db():
        try:
            payload = json.loads(asset_file.read_text(encoding="utf-8"))
            for asset in payload.get("assets", []):
                if isinstance(asset, dict) and asset.get("id"):
                    upsert_asset(str(asset["id"]), asset)
                    imported["assets"] += 1
        except (OSError, ValueError):
            pass
    batches_dir = portable_home() / "batches"
    if batches_dir.is_dir():
        for path in batches_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                upsert_batch(str(payload.get("batch_id") or path.stem), payload)
                imported["batches"] += 1
            except (OSError, ValueError):
                continue
    if db_path().is_file() or any(imported.values()):
        with contextlib.closing(connect()) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', '2')"
            )
            connection.commit()
    return {"ok": True, "imported": imported, "schema_version": 2}
