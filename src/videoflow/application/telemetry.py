"""Per-stage timing and bounded logs for one job."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

StageStatus = Literal["pending", "running", "succeeded", "failed", "cancelled"]
LogLevel = Literal["debug", "info", "warning", "error"]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@dataclass
class StageState:
    id: str
    module: str
    label: str
    status: StageStatus = "pending"
    progress: int = 0
    message: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "module": self.module,
            "label": self.label,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


@dataclass
class LogLine:
    timestamp: str
    level: LogLevel
    module: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "module": self.module,
            "message": self.message,
        }


@dataclass
class JobTelemetry:
    max_logs: int = 1000
    _stages: dict[str, StageState] = field(default_factory=dict)
    _logs: deque[LogLine] = field(default_factory=deque)
    _started: dict[str, float] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def start(self, stage: str, module: str, label: str, message: str = "") -> None:
        with self._lock:
            state = self._stages.setdefault(stage, StageState(stage, module, label))
            state.status = "running"
            state.progress = 0
            state.message = message
            state.started_at = _now()
            state.finished_at = None
            state.duration_ms = None
            state.error = None
            self._started[stage] = time.perf_counter()

    def update(self, stage: str, progress: int, message: str = "") -> None:
        with self._lock:
            state = self._stages.get(stage)
            if state is None:
                state = StageState(stage, stage, stage.title())
                self._stages[stage] = state
            state.progress = max(0, min(100, progress))
            if message:
                state.message = message

    def finish(self, stage: str, message: str = "") -> None:
        with self._lock:
            state = self._stages.get(stage)
            if state is None:
                return
            state.status = "succeeded"
            state.progress = 100
            state.finished_at = _now()
            if message:
                state.message = message
            started = self._started.pop(stage, None)
            state.duration_ms = int((time.perf_counter() - started) * 1000) if started else 0

    def fail(self, stage: str, message: str) -> None:
        with self._lock:
            state = self._stages.get(stage)
            if state is None:
                return
            state.status = "failed"
            state.finished_at = _now()
            state.message = message
            state.error = message
            started = self._started.pop(stage, None)
            state.duration_ms = int((time.perf_counter() - started) * 1000) if started else 0

    def cancel(self, stage: str, message: str = "Cancelled") -> None:
        with self._lock:
            state = self._stages.get(stage)
            if state is None:
                return
            state.status = "cancelled"
            state.finished_at = _now()
            state.message = message
            started = self._started.pop(stage, None)
            state.duration_ms = int((time.perf_counter() - started) * 1000) if started else 0

    def fail_running(self, message: str) -> None:
        with self._lock:
            for state in self._stages.values():
                if state.status == "running":
                    self.fail(state.id, message)

    def log(self, module: str, level: str, message: str) -> None:
        if not message:
            return
        with self._lock:
            if len(self._logs) >= self.max_logs:
                self._logs.popleft()
            self._logs.append(
                LogLine(
                    timestamp=datetime.now(UTC).isoformat(timespec="milliseconds"),
                    level=level,  # type: ignore[arg-type]
                    module=module,
                    message=message,
                )
            )

    def stages(self) -> list[dict[str, object]]:
        with self._lock:
            return [state.to_dict() for state in self._stages.values()]

    def log_count(self) -> int:
        with self._lock:
            return len(self._logs)

    def logs(
        self,
        *,
        module: str | None = None,
        level: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, str]]:
        with self._lock:
            rows = list(self._logs)
        if module:
            rows = [row for row in rows if row.module == module]
        if level:
            rows = [row for row in rows if row.level == level]
        return [row.to_dict() for row in rows[-max(1, limit) :]]

    def dump(self) -> str:
        with self._lock:
            rows = list(self._logs)
        return "\n".join(
            f"{row.timestamp} {row.level.upper():7} {row.module}: {row.message}" for row in rows
        ) + ("\n" if rows else "")

    def active_stage(self) -> str | None:
        with self._lock:
            for state in self._stages.values():
                if state.status == "running":
                    return state.id
        return None
