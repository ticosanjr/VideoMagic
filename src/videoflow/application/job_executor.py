"""One job lifecycle for legacy and recipe runs.

The executor owns status, retry, cancellation, persistence, and the finalizer.
Adapters only execute work and return a result. This keeps the lifecycle in one
module instead of two near-identical methods on ``JobManager``.
"""

from __future__ import annotations

import contextlib
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from videoflow.domain.errors import (
    ApprovalRequiredError,
    HumanInputRequiredError,
    JobCancelledError,
    VideoFlowError,
)

TERMINAL = frozenset({"succeeded", "failed", "cancelled", "answered"})


@dataclass(frozen=True)
class JobCallbacks:
    progress: Callable[[str, int, str], None]
    step_progress: Callable[[str, int, str], None]
    log: Callable[[str, str, str], None]
    should_cancel: Callable[[], bool]


@dataclass(frozen=True)
class JobRunPolicy:
    record_recipe_history: bool = False
    write_failure: bool = False
    cancel_error: bool = False


@dataclass
class RunOutcome:
    result: dict[str, Any] | None = None
    variants: list[dict[str, Any]] = field(default_factory=list)


class JobHost(Protocol):
    _lock: Any

    def _schedule_retry_locked(self, job: Any) -> bool: ...

    def _persist_job(self, job: Any) -> None: ...

    def _drain_queue(self) -> None: ...


class JobExecutor:
    def __init__(
        self,
        host: JobHost,
        *,
        write_log: Callable[[Any], None],
        write_failure: Callable[[Any], None],
        record_history: Callable[[Any], None],
    ) -> None:
        self._host = host
        self._write_log = write_log
        self._write_failure = write_failure
        self._record_history = record_history

    def run(
        self,
        job: Any,
        run: Callable[[Any, JobCallbacks], RunOutcome],
        policy: JobRunPolicy | None = None,
    ) -> None:
        policy = policy or JobRunPolicy()
        host = self._host
        with host._lock:
            job.status = "running"
            job.started_at = _now()
            job.message = "Starting"
            job.lease_expires_at = (
                datetime.now(UTC) + timedelta(seconds=300)
            ).isoformat(timespec="seconds")
        host._persist_job(job)
        job._last_progress_persist = time.monotonic()

        def renew_lease() -> None:
            job.lease_expires_at = (
                datetime.now(UTC) + timedelta(seconds=300)
            ).isoformat(timespec="seconds")

        def persist_progress(*, force: bool = False) -> None:
            now = time.monotonic()
            last = float(getattr(job, "_last_progress_persist", 0.0) or 0.0)
            if not force and now - last < 30.0:
                return
            job._last_progress_persist = now
            host._persist_job(job)

        def progress(stage: str, percent: int, message: str) -> None:
            with host._lock:
                changed = job.stage != stage
                job.stage = stage
                job.progress = percent
                job.message = message
                renew_lease()
                if not job.timeline_ready and (
                    job.output / "project_state.json"
                ).is_file():
                    job.timeline_ready = True
            persist_progress(force=changed)

        def step_progress(stage: str, percent: int, message: str) -> None:
            with host._lock:
                changed = job.stage != stage
                job.step_progress[stage] = max(0, min(100, int(percent)))
                job.stage = stage
                job.message = message
                renew_lease()
                if not job.timeline_ready and (
                    job.output / "project_state.json"
                ).is_file():
                    job.timeline_ready = True
                update = getattr(job.telemetry, "update", None)
                if callable(update):
                    update(stage, percent, message)
            persist_progress(force=changed)

        def log(module: str, level: str, message: str) -> None:
            job.telemetry.log(module, level, message)

        last_remote_check = 0.0

        def should_cancel() -> bool:
            nonlocal last_remote_check
            if job.cancel_requested or job.cancel_event.is_set():
                return True
            now = time.monotonic()
            if now - last_remote_check < 2.0:
                return False
            last_remote_check = now
            with contextlib.suppress(Exception):
                from videoflow.application.queue_claim import cancel_requested

                if cancel_requested(str(job.job_id)):
                    job.cancel_requested = True
                    job.cancel_event.set()
                    return True
            return False

        callbacks = JobCallbacks(progress, step_progress, log, should_cancel)
        try:
            outcome = run(job, callbacks)
            if job.finalizer is not None and not job.cancel_requested:
                job.finalizer(job)
            with host._lock:
                if job.cancel_requested:
                    job.status = "cancelled"
                    job.stage = "cancelled"
                    job.message = "Cancelled"
                else:
                    job.status = "succeeded"
                    job.progress = 100
                    job.stage = "done"
                    job.message = "Finished"
                    if (job.output / "project_state.json").is_file():
                        job.timeline_ready = True
                    payload = dict(outcome.result or {})
                    if outcome.variants:
                        payload["variants"] = outcome.variants
                    job.result = payload
        except ApprovalRequiredError as exc:
            with host._lock:
                job.status = "waiting_approval"
                job.stage = "waiting_approval"
                job.message = exc.message
                job.error = exc.to_dict()
                job.progress = max(1, min(99, job.progress))
        except HumanInputRequiredError as exc:
            with host._lock:
                job.status = "waiting_input"
                job.stage = "waiting_input"
                job.message = exc.message
                job.error = exc.to_dict()
                job.progress = max(1, min(99, job.progress))
        except JobCancelledError as exc:
            if policy.cancel_error:
                job.telemetry.fail_running(str(exc))
            with host._lock:
                if job.pause_requested:
                    job.status = "paused"
                    job.stage = "paused"
                    job.message = "Paused"
                    job.error = None
                else:
                    job.status = "cancelled"
                    job.stage = "cancelled"
                    job.message = str(exc)
                    if policy.cancel_error:
                        job.error = {
                            "ok": False,
                            "code": "job_cancelled",
                            "message": str(exc),
                        }
            if policy.write_failure:
                self._write_failure(job)
        except VideoFlowError as exc:
            job.telemetry.fail_running(exc.message)
            with host._lock:
                if host._schedule_retry_locked(job):
                    return
                job.status = "failed"
                job.stage = job.stage or "failed"
                job.message = exc.message
                job.error = exc.to_dict()
            if policy.write_failure:
                self._write_failure(job)
        except Exception as exc:  # pragma: no cover - unexpected worker failure
            traceback.print_exc()
            job.telemetry.fail_running(str(exc))
            with host._lock:
                if host._schedule_retry_locked(job):
                    return
                job.status = "failed"
                job.stage = job.stage or "failed"
                job.message = str(exc)
                job.error = {
                    "ok": False,
                    "code": "internal_error",
                    "message": str(exc),
                }
            if policy.write_failure:
                self._write_failure(job)
        finally:
            with host._lock:
                if job.status not in {"paused", "queued", "running"}:
                    job.finished_at = _now()
                if job.status in TERMINAL:
                    job.lease_expires_at = ""
                if (job.output / "project_state.json").is_file():
                    job.timeline_ready = True
            if not job.deleted:
                self._write_log(job)
                if policy.record_recipe_history:
                    self._record_history(job)
                host._persist_job(job)
            elif job.status == "cancelled":
                self._write_log(job)
            host._drain_queue()


def _now() -> str:
    from videoflow.application.clock import now_iso_ms

    return now_iso_ms()
