"""SQLite operational index for jobs, assets, and backups."""

from __future__ import annotations

import contextlib
import json
import logging
import shutil
import sqlite3
import threading
import zipfile
from pathlib import Path
from typing import Any

from videoflow.application.clock import now_iso as _now
from videoflow.runtime import portable_home

DB_FILE = "videoflow.db"
logger = logging.getLogger(__name__)
_initialized: set[str] = set()
_init_lock = threading.Lock()
_error_lock = threading.Lock()
_last_error = ""


def last_error() -> str:
    with _error_lock:
        return _last_error


def _set_error(message: str) -> None:
    global _last_error
    with _error_lock:
        _last_error = message
    if message:
        logger.warning("%s", message)


def db_path() -> Path:
    return portable_home() / DB_FILE


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS jobs ("
        "job_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL, "
        "status TEXT, priority INTEGER DEFAULT 0, attempts INTEGER DEFAULT 0, "
        "next_run TEXT, lease_expires TEXT, progress INTEGER DEFAULT 0, "
        "source TEXT, output TEXT, recipe TEXT, variables TEXT, "
        "project_id TEXT, created_at TEXT, started_at TEXT, finished_at TEXT, "
        "cancel_requested INTEGER DEFAULT 0, current_step TEXT, step_index INTEGER DEFAULT 0, "
        "total_steps INTEGER DEFAULT 0, eta_sec REAL DEFAULT 0)"
    )
    existing = {row[1] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()}
    for column, definition in (
        ("updated_at", "TEXT"),
        ("status", "TEXT"),
        ("priority", "INTEGER DEFAULT 0"),
        ("attempts", "INTEGER DEFAULT 0"),
        ("next_run", "TEXT"),
        ("lease_expires", "TEXT"),
        ("progress", "INTEGER DEFAULT 0"),
        ("source", "TEXT"),
        ("output", "TEXT"),
        ("recipe", "TEXT"),
        ("variables", "TEXT"),
        ("project_id", "TEXT"),
        ("created_at", "TEXT"),
        ("started_at", "TEXT"),
        ("finished_at", "TEXT"),
        ("cancel_requested", "INTEGER DEFAULT 0"),
        ("current_step", "TEXT"),
        ("step_index", "INTEGER DEFAULT 0"),
        ("total_steps", "INTEGER DEFAULT 0"),
        ("eta_sec", "REAL DEFAULT 0"),
    ):
        if column not in existing:
            connection.execute(f"ALTER TABLE jobs ADD COLUMN {column} {definition}")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id, updated_at)"
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, updated_at)")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS assets ("
        "asset_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS batches ("
        "batch_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS projects ("
        "project_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS styles ("
        "style_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    connection.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1')")


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.is_file()
    key = str(path.resolve())
    connection = sqlite3.connect(path, timeout=15.0)
    connection.execute("PRAGMA busy_timeout=15000")
    connection.execute("PRAGMA synchronous=NORMAL")
    with _init_lock:
        if fresh or key not in _initialized:
            connection.execute("PRAGMA journal_mode=WAL")
            _create_schema(connection)
            _initialized.add(key)
        else:
            connection.execute("PRAGMA journal_mode=WAL")
    connection.commit()
    _set_error("")
    return connection


def upsert_job(job_id: str, payload: dict[str, Any]) -> None:
    try:
        with contextlib.closing(connect()) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO jobs ("
                "job_id, payload, updated_at, status, priority, attempts, next_run, "
                "lease_expires, progress, source, output, recipe, variables, "
                "project_id, created_at, started_at, finished_at, cancel_requested, "
                "current_step, step_index, total_steps, eta_sec"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    json.dumps(payload, sort_keys=True),
                    _now(),
                    str(payload.get("status") or ""),
                    int(payload.get("priority") or 0),
                    int(payload.get("attempts") or 0),
                    str(payload.get("next_run") or ""),
                    str(payload.get("lease_expires_at") or ""),
                    int(payload.get("progress") or 0),
                    str(payload.get("source") or ""),
                    str(payload.get("output") or ""),
                    str((payload.get("options") or {}).get("recipe_id") or ""),
                    json.dumps(payload.get("options") or {}, sort_keys=True),
                    str(payload.get("project_id") or ""),
                    str(payload.get("created_at") or ""),
                    str(payload.get("started_at") or ""),
                    str(payload.get("finished_at") or ""),
                    1 if payload.get("cancel_requested") else 0,
                    str(payload.get("current_step") or ""),
                    int(payload.get("step_index") or 0),
                    int(payload.get("total_steps") or 0),
                    float(payload.get("eta_sec") or 0.0),
                ),
            )
            connection.commit()
    except sqlite3.Error as exc:
        _set_error(f"could not persist job {job_id}: {exc}")


def upsert_project(project_id: str, payload: dict[str, Any]) -> None:
    try:
        with contextlib.closing(connect()) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO projects (project_id, payload, updated_at) "
                "VALUES (?, ?, ?)",
                (project_id, json.dumps(payload, sort_keys=True), _now()),
            )
            connection.commit()
    except sqlite3.Error as exc:
        _set_error(f"could not persist project {project_id}: {exc}")


def get_project(project_id: str) -> dict[str, Any] | None:
    if not db_path().is_file():
        return None
    try:
        with contextlib.closing(connect()) as connection:
            row = connection.execute(
                "SELECT payload FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
    except sqlite3.Error as exc:
        _set_error(f"could not read project {project_id}: {exc}")
        return None
    if row is None:
        return None
    try:
        payload = json.loads(str(row[0]))
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def delete_project(project_id: str) -> None:
    try:
        with contextlib.closing(connect()) as connection:
            connection.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
            connection.commit()
    except sqlite3.Error as exc:
        _set_error(f"could not delete project {project_id}: {exc}")


def list_projects() -> list[dict[str, Any]]:
    if not db_path().is_file():
        return []
    try:
        with contextlib.closing(connect()) as connection:
            rows = connection.execute(
                "SELECT payload FROM projects ORDER BY updated_at DESC"
            ).fetchall()
    except sqlite3.Error as exc:
        _set_error(f"could not read projects: {exc}")
        return []
    payloads: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(str(row[0]))
        except ValueError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def list_jobs(
    *,
    status: str = "",
    project_id: str = "",
    job_id: str = "",
    limit: int | None = None,
) -> list[dict[str, Any]]:
    if not db_path().is_file():
        return []
    clauses: list[str] = []
    values: list[Any] = []
    if status:
        clauses.append("status = ?")
        values.append(status)
    if project_id:
        clauses.append("project_id = ?")
        values.append(project_id)
    if job_id:
        clauses.append("job_id = ?")
        values.append(job_id)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"SELECT payload FROM jobs{where} ORDER BY updated_at DESC"
    if limit is not None:
        query += " LIMIT ?"
        values.append(max(0, int(limit)))
    try:
        with contextlib.closing(connect()) as connection:
            rows = connection.execute(query, values).fetchall()
    except sqlite3.Error as exc:
        _set_error(f"could not read jobs: {exc}")
        return []
    _set_error("")
    result: list[dict[str, Any]] = []
    for (payload,) in rows:
        try:
            result.append(json.loads(payload))
        except ValueError:
            continue
    return result


def request_job_cancel(job_id: str, *, force: bool = False) -> dict[str, Any] | None:
    """Mark a job as cancellation-requested in the shared store."""

    try:
        with contextlib.closing(connect()) as connection:
            row = connection.execute(
                "SELECT payload FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                return None
            payload = json.loads(str(row[0]))
            if not isinstance(payload, dict):
                return None
            payload["cancel_requested"] = True
            if force or payload.get("status") in {"queued", "paused"}:
                payload["status"] = "cancelled"
                payload["stage"] = "cancelled"
                payload["message"] = "Cancelled"
            else:
                payload["message"] = "Cancellation requested"
            connection.execute(
                "UPDATE jobs SET payload = ?, cancel_requested = 1, status = ?, updated_at = ? "
                "WHERE job_id = ?",
                (
                    json.dumps(payload, sort_keys=True),
                    str(payload.get("status") or ""),
                    _now(),
                    job_id,
                ),
            )
            connection.commit()
            return payload
    except (sqlite3.Error, ValueError) as exc:
        _set_error(f"could not cancel job {job_id}: {exc}")
        return None


def job_cancel_requested(job_id: str) -> bool:
    if not db_path().is_file():
        return False
    try:
        with contextlib.closing(connect()) as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
    except sqlite3.Error:
        return False
    return bool(row and row[0])


def delete_job(job_id: str) -> None:
    try:
        with contextlib.closing(connect()) as connection:
            connection.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            connection.commit()
    except sqlite3.Error as exc:
        _set_error(f"could not delete job {job_id}: {exc}")


def upsert_assets(items: list[tuple[str, dict[str, Any]]]) -> None:
    if not items:
        return
    try:
        with contextlib.closing(connect()) as connection:
            now = _now()
            connection.executemany(
                "INSERT OR REPLACE INTO assets (asset_id, payload, updated_at) VALUES (?, ?, ?)",
                [
                    (asset_id, json.dumps(payload, sort_keys=True), now)
                    for asset_id, payload in items
                ],
            )
            connection.commit()
    except sqlite3.Error as exc:
        _set_error(f"could not persist assets: {exc}")


def upsert_asset(asset_id: str, payload: dict[str, Any]) -> None:
    upsert_assets([(asset_id, payload)])


def list_assets_db(
    *, limit: int | None = None, offset: int = 0, query: str = "", kind: str = ""
) -> list[dict[str, Any]]:
    if not db_path().is_file():
        return []
    try:
        with contextlib.closing(connect()) as connection:
            clauses = []
            params: list[Any] = []
            if kind:
                clauses.append("json_extract(payload, '$.kind') = ?")
                params.append(kind)
            if query:
                clauses.append(
                    "(lower(json_extract(payload, '$.name')) LIKE ? OR lower(payload) LIKE ?)"
                )
                params.extend([f"%{query.lower()}%", f"%{query.lower()}%"])
            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            sql = f"SELECT payload FROM assets{where} ORDER BY updated_at DESC"
            if limit is not None:
                sql += " LIMIT ? OFFSET ?"
                params.extend([max(1, int(limit)), max(0, int(offset))])
            rows = connection.execute(sql, params).fetchall()
    except sqlite3.Error as exc:
        _set_error(f"could not read assets: {exc}")
        return []
    _set_error("")
    result: list[dict[str, Any]] = []
    for (payload,) in rows:
        try:
            result.append(json.loads(payload))
        except ValueError:
            continue
    return result


def upsert_style(style_id: str, payload: dict[str, Any]) -> None:
    try:
        with contextlib.closing(connect()) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO styles (style_id, payload, updated_at) VALUES (?, ?, ?)",
                (style_id, json.dumps(payload, sort_keys=True), _now()),
            )
            connection.commit()
    except sqlite3.Error as exc:
        _set_error(f"could not persist style {style_id}: {exc}")


def delete_style(style_id: str) -> None:
    try:
        with contextlib.closing(connect()) as connection:
            connection.execute("DELETE FROM styles WHERE style_id = ?", (style_id,))
            connection.commit()
    except sqlite3.Error as exc:
        _set_error(f"could not delete style {style_id}: {exc}")


def list_styles_db() -> list[dict[str, Any]]:
    if not db_path().is_file():
        return []
    try:
        with contextlib.closing(connect()) as connection:
            rows = connection.execute(
                "SELECT payload FROM styles ORDER BY style_id"
            ).fetchall()
    except sqlite3.Error as exc:
        _set_error(f"could not read styles: {exc}")
        return []
    _set_error("")
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
            rows = connection.execute("SELECT payload FROM batches ORDER BY updated_at").fetchall()
    except sqlite3.Error as exc:
        _set_error(f"could not read batches: {exc}")
        return []
    _set_error("")
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
    except sqlite3.Error as exc:
        _set_error(f"could not persist batch {batch_id}: {exc}")


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
        _set_error(f"database integrity check failed: {exc}")
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
            try:
                check = sqlite3.connect(temp_db)
                try:
                    integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
                finally:
                    check.close()
            except sqlite3.DatabaseError as exc:
                temp_db.unlink(missing_ok=True)
                raise ValueError(f"Backup database is unreadable: {exc}") from exc
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
    known_jobs = {str(payload.get("job_id") or "") for payload in list_jobs()}
    if jobs_dir.is_dir():
        for path in jobs_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                job_id = str(payload.get("job_id") or path.stem)
                if job_id in known_jobs:
                    continue
                upsert_job(job_id, payload)
                known_jobs.add(job_id)
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
    known_batches = {str(payload.get("batch_id") or "") for payload in list_batches()}
    if batches_dir.is_dir():
        for path in batches_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                batch_id = str(payload.get("batch_id") or path.stem)
                if batch_id in known_batches:
                    continue
                upsert_batch(batch_id, payload)
                known_batches.add(batch_id)
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
