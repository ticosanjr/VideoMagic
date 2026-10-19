"""In-process job manager for the portable pipeline.

One process, a bounded number of workers, in-memory state. A restart loses job
history but never damages a project already written to disk.
"""

from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from videoflow.application.portable import run_portable
from videoflow.domain.config import JlCutsConfig, ZoomsConfig
from videoflow.domain.errors import (
    JobCancelledError,
    JobNotFoundError,
    JobQueueFullError,
    VideoFlowError,
)
from videoflow.exporters.fcpxml import Dialect

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
TERMINAL: frozenset[str] = frozenset({"succeeded", "failed", "cancelled"})
Runner = Callable[..., Any]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class Job:
    source: Path
    output: Path
    options: dict[str, Any]
    job_id: UUID = field(default_factory=uuid4)
    status: JobStatus = "queued"
    progress: int = 0
    stage: str = "queued"
    message: str = "Waiting for a worker"
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    cancel_requested: bool = False
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": str(self.job_id),
            "status": self.status,
            "progress": self.progress,
            "stage": self.stage,
            "message": self.message,
            "source": str(self.source),
            "output": str(self.output),
            "options": self.options,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class JobManager:
    def __init__(
        self,
        runner: Runner = run_portable,
        *,
        max_active: int = 2,
        history: int = 50,
    ) -> None:
        self._runner = runner
        self._max_active = max_active
        self._history = history
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def start(
        self,
        source: Path,
        output: Path,
        options: dict[str, Any] | None = None,
    ) -> Job:
        with self._lock:
            self._prune()
            active = sum(1 for job in self._jobs.values() if job.status not in TERMINAL)
            if active >= self._max_active:
                raise JobQueueFullError(
                    f"{self._max_active} jobs are already active. Wait or cancel one."
                )
            job = Job(
                source=Path(source),
                output=Path(output),
                options=dict(options or {}),
            )
            self._jobs[str(job.job_id)] = job
        thread = threading.Thread(
            target=self._work,
            args=(job,),
            name=f"videoflow-job-{job.job_id}",
            daemon=True,
        )
        thread.start()
        return job

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(f"Unknown job: {job_id}")
            return job

    def list(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)

    def cancel(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(f"Unknown job: {job_id}")
            if job.status in TERMINAL:
                return job
            job.cancel_requested = True
            if job.status == "queued":
                job.status = "cancelled"
                job.stage = "cancelled"
                job.message = "Cancelled before starting"
                job.finished_at = _now()
            else:
                job.message = "Cancellation requested"
            return job

    def _work(self, job: Job) -> None:
        with self._lock:
            job.status = "running"
            job.started_at = _now()
            job.message = "Starting"
        options = job.options
        jl = JlCutsConfig(
            enable_j_cuts=bool(options.get("jcut", True)),
            enable_l_cuts=bool(options.get("lcut", False)),
        )
        zooms = ZoomsConfig(mode="alternate_cuts" if options.get("zooms", True) else "manual_rules")
        dialect: Dialect = options.get("dialect", "1.9")

        def progress(stage: str, percent: int, message: str) -> None:
            with self._lock:
                job.stage = stage
                job.progress = percent
                job.message = message

        def should_cancel() -> bool:
            return job.cancel_requested

        try:
            result = self._runner(
                job.source,
                job.output,
                noise_db=float(options.get("noise_db", -30.0)),
                min_silence_ms=int(options.get("min_silence_ms", 400)),
                jl=jl,
                zooms=zooms,
                dialect=dialect,
                progress=progress,
                should_cancel=should_cancel,
            )
            with self._lock:
                if job.cancel_requested:
                    job.status = "cancelled"
                    job.stage = "cancelled"
                    job.message = "Cancelled"
                else:
                    job.status = "succeeded"
                    job.progress = 100
                    job.stage = "done"
                    job.message = "Finished"
                    job.result = _result_dict(result)
        except JobCancelledError as exc:
            with self._lock:
                job.status = "cancelled"
                job.stage = "cancelled"
                job.message = str(exc)
        except VideoFlowError as exc:
            with self._lock:
                job.status = "failed"
                job.stage = job.stage or "failed"
                job.message = exc.message
                job.error = exc.to_dict()
        except Exception as exc:  # pragma: no cover - unexpected worker failure
            traceback.print_exc()
            with self._lock:
                job.status = "failed"
                job.stage = job.stage or "failed"
                job.message = str(exc)
                job.error = {
                    "ok": False,
                    "code": "internal_error",
                    "message": str(exc),
                }
        finally:
            with self._lock:
                job.finished_at = _now()

    def _prune(self) -> None:
        finished = [job for job in self._jobs.values() if job.status in TERMINAL]
        if len(finished) <= self._history:
            return
        finished.sort(key=lambda item: item.finished_at or "")
        for job in finished[: len(finished) - self._history]:
            self._jobs.pop(str(job.job_id), None)


def _result_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_dict"):
        payload = result.to_dict()
        if isinstance(payload, dict):
            return payload
    if isinstance(result, dict):
        return result
    return {"ok": True, "result": str(result)}
