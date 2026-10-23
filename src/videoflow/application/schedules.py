"""Persistent recipe schedules, watch folders, and retry policy.

The schedule table lives in SQLite (`videoflow.db`) with a one-time migration
from the legacy `recipe-schedules.json` file. Each schedule keeps a bounded run
history and a per-file watch signature based on size and modification time.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from videoflow.domain.errors import StateNotReadyError
from videoflow.domain.paths import resolve_allowed
from videoflow.engine.recipes import get_recipe, resolve_recipe_paths
from videoflow.runtime import allowed_roots, portable_home

LEGACY_FILE = "recipe-schedules.json"
DB_FILE = "videoflow.db"
MAX_RUNS = 20


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class RecipeSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex[:10], min_length=1, max_length=40)
    kind: Literal["once", "interval", "watch"] = "interval"
    recipe_id: str = Field(min_length=1)
    source: str = ""
    output: str = ""
    interval_seconds: int = Field(default=3600, ge=30, le=604800)
    watch_dir: str = ""
    pattern: str = "*.mp4"
    enabled: bool = True
    last_run: str = ""
    next_run: str = ""
    status: str = "idle"
    last_error: str = ""
    attempts: int = Field(default=0, ge=0)
    max_retries: int = Field(default=5, ge=0, le=20)
    created_at: str = Field(default_factory=_now)
    seen_paths: list[str] = Field(default_factory=list)
    seen_files: list[dict[str, object]] = Field(default_factory=list)
    runs: list[dict[str, object]] = Field(default_factory=list)

    def record_run(self, *, job_id: str = "", status: str, error: str = "") -> None:
        self.runs.append(
            {
                "at": _now(),
                "job_id": job_id,
                "status": status,
                "error": error,
            }
        )
        self.runs = self.runs[-MAX_RUNS:]


def db_path() -> Path:
    return portable_home() / DB_FILE


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10.0)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schedules ("
        "id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    return connection


def _migrate_legacy(connection: sqlite3.Connection) -> None:
    legacy = portable_home() / LEGACY_FILE
    if not legacy.is_file():
        return
    count = connection.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]
    if count:
        return
    try:
        payload = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    for item in payload.get("items", []) if isinstance(payload, dict) else []:
        try:
            schedule = RecipeSchedule.model_validate(item)
        except ValueError:
            continue
        connection.execute(
            "INSERT OR REPLACE INTO schedules (id, payload, updated_at) VALUES (?, ?, ?)",
            (schedule.id, schedule.model_dump_json(), _now()),
        )
    connection.commit()


def load_schedules() -> list[RecipeSchedule]:
    with _connect() as connection:
        _migrate_legacy(connection)
        rows = connection.execute(
            "SELECT payload FROM schedules ORDER BY updated_at"
        ).fetchall()
    result: list[RecipeSchedule] = []
    for (payload,) in rows:
        try:
            result.append(RecipeSchedule.model_validate_json(payload))
        except ValueError:
            continue
    return result


def save_schedules(items: list[RecipeSchedule]) -> list[RecipeSchedule]:
    with _connect() as connection:
        _migrate_legacy(connection)
        for item in items:
            connection.execute(
                "INSERT OR REPLACE INTO schedules (id, payload, updated_at) VALUES (?, ?, ?)",
                (item.id, item.model_dump_json(), _now()),
            )
        connection.commit()
    return items


def upsert_schedule(schedule: RecipeSchedule) -> RecipeSchedule:
    if schedule.kind in {"once", "interval"}:
        if not schedule.source:
            raise StateNotReadyError("A schedule needs a source file.")
        if not schedule.output:
            raise StateNotReadyError("A schedule needs an output directory.")
    if schedule.kind == "watch" and not schedule.watch_dir:
        raise StateNotReadyError("A watch folder needs a directory.")
    with _connect() as connection:
        _migrate_legacy(connection)
        connection.execute(
            "INSERT OR REPLACE INTO schedules (id, payload, updated_at) VALUES (?, ?, ?)",
            (schedule.id, schedule.model_dump_json(), _now()),
        )
        connection.commit()
    return schedule


def delete_schedule(schedule_id: str) -> None:
    with _connect() as connection:
        cursor = connection.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        connection.commit()
        if cursor.rowcount == 0:
            raise StateNotReadyError(f"Unknown schedule: {schedule_id}")


def _submit(jobs: Any, schedule: RecipeSchedule, source: Path, output: Path) -> str:
    roots = allowed_roots()
    source = resolve_allowed(source, roots)
    output = resolve_allowed(output, roots)
    if not source.is_file():
        raise StateNotReadyError(f"Source does not exist: {source}")
    recipe = get_recipe(schedule.recipe_id)
    recipe = resolve_recipe_paths(recipe, roots)
    job = jobs.start(
        source,
        output,
        {"mode": "recipe", "recipe": recipe.model_dump(mode="json"), "resume": True},
    )
    return str(job.job_id)


def _signature(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {"path": str(path), "size": stat.st_size, "mtime": stat.st_mtime}


def run_schedule(jobs: Any, schedule: RecipeSchedule) -> RecipeSchedule:
    try:
        if schedule.kind == "watch":
            watch = Path(schedule.watch_dir).expanduser()
            if not watch.is_dir():
                raise StateNotReadyError(f"Watch folder does not exist: {watch}")
            seen = {
                str(item.get("path")): (item.get("size"), item.get("mtime"))
                for item in schedule.seen_files
            }
            pending: list[Path] = []
            for path in sorted(watch.glob(schedule.pattern or "*")):
                if not path.is_file():
                    continue
                signature = _signature(path)
                previous = seen.get(str(path))
                if previous == (signature["size"], signature["mtime"]):
                    continue
                pending.append(path)
                if len(pending) >= 10:
                    break
            if not pending:
                schedule.status = "waiting"
                schedule.last_error = ""
                schedule.next_run = (
                    datetime.now(UTC) + timedelta(seconds=20)
                ).isoformat(timespec="seconds")
                return schedule
            submitted = 0
            for path in pending:
                output = Path(schedule.output).expanduser() / f"{path.stem}-videoflow"
                try:
                    job_id = _submit(jobs, schedule, path, output)
                except Exception as exc:
                    schedule.last_error = str(exc)
                    continue
                signature = _signature(path)
                schedule.seen_files.append(signature)
                schedule.seen_paths.append(str(path))
                schedule.record_run(job_id=job_id, status="queued")
                submitted += 1
            schedule.seen_files = schedule.seen_files[-1000:]
            schedule.seen_paths = schedule.seen_paths[-1000:]
            schedule.status = f"queued {submitted}"
            schedule.last_run = _now()
            schedule.attempts = 0
            schedule.next_run = (
                datetime.now(UTC) + timedelta(seconds=20)
            ).isoformat(timespec="seconds")
            return schedule
        if not schedule.source:
            raise StateNotReadyError("Schedule has no source.")
        if (
            schedule.kind == "interval"
            and schedule.last_run
            and datetime.now(UTC) - _parse(schedule.last_run)
            < timedelta(seconds=schedule.interval_seconds)
        ):
            return schedule
        job_id = _submit(jobs, schedule, Path(schedule.source), Path(schedule.output))
        schedule.last_run = _now()
        schedule.status = "queued"
        schedule.last_error = ""
        schedule.attempts = 0
        schedule.next_run = ""
        schedule.record_run(job_id=job_id, status="queued")
        if schedule.kind == "once":
            schedule.enabled = False
    except Exception as exc:
        schedule.attempts += 1
        schedule.last_error = str(exc)
        schedule.record_run(status="failed", error=str(exc))
        if schedule.attempts > schedule.max_retries:
            schedule.status = "failed"
            schedule.next_run = ""
        else:
            backoff = min(3600, 30 * (2 ** max(0, schedule.attempts - 1)))
            schedule.status = f"retry in {backoff}s"
            schedule.next_run = (
                datetime.now(UTC) + timedelta(seconds=backoff)
            ).isoformat(timespec="seconds")
    return schedule


def run_due(jobs: Any) -> list[RecipeSchedule]:
    items = load_schedules()
    changed = False
    now = datetime.now(UTC)
    for schedule in items:
        if not schedule.enabled:
            continue
        if schedule.next_run and _parse(schedule.next_run) > now:
            continue
        before = schedule.model_dump(mode="json")
        run_schedule(jobs, schedule)
        if schedule.model_dump(mode="json") != before:
            changed = True
    if changed:
        save_schedules(items)
    return items


def run_now(jobs: Any, schedule_id: str) -> RecipeSchedule:
    items = load_schedules()
    schedule = next((item for item in items if item.id == schedule_id), None)
    if schedule is None:
        raise StateNotReadyError(f"Unknown schedule: {schedule_id}")
    run_schedule(jobs, schedule)
    save_schedules(items)
    return schedule


class RecipeScheduler:
    def __init__(self, jobs: Any, interval: float = 20.0) -> None:
        self.jobs = jobs
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> RecipeScheduler:
        if self._thread is not None and self._thread.is_alive():
            return self
        self._thread = threading.Thread(
            target=self._run, name="videoflow-recipe-scheduler", daemon=True
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                run_due(self.jobs)
            except Exception:
                continue


_scheduler: RecipeScheduler | None = None


def start_recipe_scheduler(jobs: Any) -> RecipeScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = RecipeScheduler(jobs)
    return _scheduler.start()


def stop_recipe_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.stop()
        _scheduler = None
