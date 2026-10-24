"""Local service definitions with start/stop, health checks, and logs."""

from __future__ import annotations

import json
import os
import shutil
import signal
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field

from videoflow.domain.errors import StateNotReadyError
from videoflow.runtime import portable_home

DB_FILE = "videoflow.db"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ServiceDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str = Field(min_length=1, max_length=120)
    command: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    cwd: str = ""
    env: dict[str, str] = Field(default_factory=dict)
    port: int = Field(default=0, ge=0, le=65535)
    health_url: str = ""
    autostart: bool = False
    enabled: bool = True


@dataclass
class RunningService:
    definition: ServiceDefinition
    process: subprocess.Popen[bytes] = field(repr=False)
    started_at: str = field(default_factory=_now)
    last_error: str = ""
    log_path: Path = field(default_factory=Path)


def _connect() -> sqlite3.Connection:
    path = portable_home() / DB_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10.0)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS service_definitions ("
        "id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    return connection


def load_definitions() -> list[ServiceDefinition]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT payload FROM service_definitions ORDER BY updated_at"
        ).fetchall()
    result: list[ServiceDefinition] = []
    for (payload,) in rows:
        try:
            result.append(ServiceDefinition.model_validate_json(payload))
        except ValueError:
            continue
    return result


def list_definitions() -> list[ServiceDefinition]:
    return load_definitions()


def save_definition(definition: ServiceDefinition) -> ServiceDefinition:
    with _connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO service_definitions (id, payload, updated_at) "
            "VALUES (?, ?, ?)",
            (definition.id, definition.model_dump_json(), _now()),
        )
        connection.commit()
    return definition


def delete_definition(definition_id: str) -> None:
    stop_service(definition_id)
    with _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM service_definitions WHERE id = ?", (definition_id,)
        )
        connection.commit()
        if cursor.rowcount == 0:
            raise StateNotReadyError(f"Unknown service: {definition_id}")


def _logs_dir() -> Path:
    path = portable_home() / "service-logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


_RUNNING: dict[str, RunningService] = {}


def rotate_service_log(path: Path, *, max_bytes: int = 4_000_000, keep: int = 2) -> bool:
    if not path.is_file() or path.stat().st_size <= max_bytes:
        return False
    for index in range(keep - 1, 0, -1):
        source = path.with_suffix(f".log.{index}")
        if source.exists():
            source.replace(path.with_suffix(f".log.{index + 1}"))
    path.replace(path.with_suffix(".log.1"))
    return True


def _resolve_command(command: str) -> str:
    path = Path(command).expanduser()
    if path.is_file():
        return str(path)
    found = shutil.which(command)
    if found:
        return found
    raise StateNotReadyError(f"Service command not found: {command}")


def start_service(definition_id: str) -> dict[str, object]:
    definition = next(
        (item for item in load_definitions() if item.id == definition_id), None
    )
    if definition is None:
        raise StateNotReadyError(f"Unknown service: {definition_id}")
    if not definition.enabled:
        raise StateNotReadyError(f"Service is disabled: {definition_id}")
    running = _RUNNING.get(definition_id)
    if running is not None and running.process.poll() is None:
        return status_service(definition_id)
    command = _resolve_command(definition.command)
    log_path = _logs_dir() / f"{definition.id}.log"
    env = {**os.environ, **definition.env}
    cwd = definition.cwd or None
    handle = log_path.open("ab")
    try:
        process = subprocess.Popen(
            [command, *definition.args],
            cwd=cwd,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        handle.close()
        raise StateNotReadyError(f"Could not start {definition.id}: {exc}") from exc
    handle.close()
    _RUNNING[definition.id] = RunningService(
        definition=definition,
        process=process,
        log_path=log_path,
    )
    return status_service(definition_id)


def stop_service(definition_id: str) -> dict[str, object]:
    running = _RUNNING.get(definition_id)
    if running is None:
        return {"id": definition_id, "status": "stopped", "pid": None}
    process = running.process
    if process.poll() is None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (OSError, ProcessLookupError):
                process.kill()
            process.wait(timeout=5)
    _RUNNING.pop(definition_id, None)
    return {"id": definition_id, "status": "stopped", "pid": None}


def _health(url: str) -> bool | None:
    if not url:
        return None
    try:
        with httpx.Client(timeout=2.0) as client:
            response = client.get(url)
        return 200 <= response.status_code < 400
    except httpx.HTTPError:
        return False


def status_service(definition_id: str) -> dict[str, object]:
    definition = next(
        (item for item in load_definitions() if item.id == definition_id), None
    )
    if definition is None:
        raise StateNotReadyError(f"Unknown service: {definition_id}")
    running = _RUNNING.get(definition_id)
    if running is None:
        return {
            "id": definition.id,
            "name": definition.name,
            "status": "stopped",
            "pid": None,
            "healthy": None,
            "port": definition.port,
            "started_at": "",
            "last_error": "",
        }
    code = running.process.poll()
    status = "running" if code is None else "exited"
    healthy = _health(definition.health_url) if code is None else None
    return {
        "id": definition.id,
        "name": definition.name,
        "status": status,
        "pid": running.process.pid if code is None else None,
        "healthy": healthy,
        "port": definition.port,
        "started_at": running.started_at,
        "last_error": running.last_error or (f"exit {code}" if code is not None else ""),
    }


def list_statuses() -> list[dict[str, object]]:
    return [status_service(item.id) for item in load_definitions()]


def read_logs(definition_id: str, lines: int = 200) -> str:
    path = _logs_dir() / f"{definition_id}.log"
    if not path.is_file():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-max(1, lines) :])


def autostart() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for definition in load_definitions():
        if not definition.enabled or not definition.autostart:
            continue
        try:
            result.append(start_service(definition.id))
        except Exception:
            continue
    return result


def stop_all() -> None:
    for definition_id in list(_RUNNING):
        stop_service(definition_id)


def export_definitions() -> str:
    return json.dumps(
        {"services": [item.model_dump(mode="json") for item in load_definitions()]},
        indent=2,
    )
