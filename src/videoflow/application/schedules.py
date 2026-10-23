"""Persistent recipe schedules and watch folders."""

from __future__ import annotations

import json
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

SCHEDULE_FILE = "recipe-schedules.json"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


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
    status: str = "idle"
    last_error: str = ""
    created_at: str = Field(default_factory=_now)
    seen_paths: list[str] = Field(default_factory=list)


def schedules_path() -> Path:
    return portable_home() / SCHEDULE_FILE


def load_schedules() -> list[RecipeSchedule]:
    path = schedules_path()
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    result: list[RecipeSchedule] = []
    for item in payload.get("items", []) if isinstance(payload, dict) else []:
        try:
            result.append(RecipeSchedule.model_validate(item))
        except ValueError:
            continue
    return result


def save_schedules(items: list[RecipeSchedule]) -> list[RecipeSchedule]:
    path = schedules_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"items": [item.model_dump(mode="json") for item in items]}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return items


def upsert_schedule(schedule: RecipeSchedule) -> RecipeSchedule:
    if schedule.kind in {"once", "interval"}:
        if not schedule.source:
            raise StateNotReadyError("A schedule needs a source file.")
        if not schedule.output:
            raise StateNotReadyError("A schedule needs an output directory.")
    if schedule.kind == "watch" and not schedule.watch_dir:
        raise StateNotReadyError("A watch folder needs a directory.")
    items = [item for item in load_schedules() if item.id != schedule.id]
    items.append(schedule)
    save_schedules(items)
    return schedule


def delete_schedule(schedule_id: str) -> None:
    items = load_schedules()
    remaining = [item for item in items if item.id != schedule_id]
    if len(remaining) == len(items):
        raise StateNotReadyError(f"Unknown schedule: {schedule_id}")
    save_schedules(remaining)


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


def run_schedule(jobs: Any, schedule: RecipeSchedule) -> RecipeSchedule:
    try:
        if schedule.kind == "watch":
            watch = Path(schedule.watch_dir).expanduser()
            if not watch.is_dir():
                raise StateNotReadyError(f"Watch folder does not exist: {watch}")
            seen = set(schedule.seen_paths)
            pending = [
                path
                for path in sorted(watch.glob(schedule.pattern or "*"))
                if path.is_file() and str(path) not in seen
            ][:10]
            if not pending:
                schedule.status = "waiting"
                schedule.last_error = ""
                return schedule
            submitted = 0
            for path in pending:
                output = Path(schedule.output).expanduser() / f"{path.stem}-videoflow"
                try:
                    _submit(jobs, schedule, path, output)
                except Exception as exc:
                    schedule.last_error = str(exc)
                    continue
                schedule.seen_paths.append(str(path))
                submitted += 1
            schedule.seen_paths = schedule.seen_paths[-1000:]
            schedule.status = f"queued {submitted}"
            schedule.last_run = _now()
            return schedule
        if not schedule.source:
            raise StateNotReadyError("Schedule has no source.")
        if schedule.kind == "interval" and schedule.last_run:
            previous = datetime.fromisoformat(schedule.last_run)
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=UTC)
            if datetime.now(UTC) - previous < timedelta(seconds=schedule.interval_seconds):
                return schedule
        _submit(jobs, schedule, Path(schedule.source), Path(schedule.output))
        schedule.last_run = _now()
        schedule.status = "queued"
        schedule.last_error = ""
        if schedule.kind == "once":
            schedule.enabled = False
    except Exception as exc:
        schedule.status = "failed"
        schedule.last_error = str(exc)
    return schedule


def run_due(jobs: Any) -> list[RecipeSchedule]:
    items = load_schedules()
    changed = False
    for schedule in items:
        if not schedule.enabled:
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
