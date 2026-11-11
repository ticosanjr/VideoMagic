from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

from videoflow.application.job_executor import (
    JobCallbacks,
    JobExecutor,
    JobRunPolicy,
    RunOutcome,
)
from videoflow.domain.errors import JobCancelledError


class Telemetry:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str, str]] = []
        self.failed: list[str] = []
        self.updates: list[tuple[str, int, str]] = []

    def log(self, module: str, level: str, message: str) -> None:
        self.lines.append((module, level, message))

    def update(self, stage: str, percent: int, message: str) -> None:
        self.updates.append((stage, percent, message))

    def fail_running(self, message: str) -> None:
        self.failed.append(message)


class Host:
    def __init__(self, output: Path) -> None:
        self._lock = threading.RLock()
        self.persisted = 0
        self.drained = 0
        self.retry = False
        self.written = 0
        self.failures = 0
        self.history = 0
        self.output = output

    def _schedule_retry_locked(self, job: object) -> bool:
        if self.retry:
            job.status = "queued"
        return self.retry

    def _persist_job(self, job: object) -> None:
        self.persisted += 1

    def _drain_queue(self) -> None:
        self.drained += 1


def _job(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        status="queued",
        started_at="",
        finished_at="",
        message="",
        lease_expires_at="",
        stage="",
        progress=0,
        timeline_ready=False,
        step_progress={},
        output=tmp_path,
        cancel_requested=False,
        cancel_event=threading.Event(),
        pause_requested=False,
        deleted=False,
        finalizer=None,
        telemetry=Telemetry(),
        result=None,
        error=None,
    )


def _executor(host: Host) -> JobExecutor:
    def write_log(job: object) -> None:
        host.written += 1

    def write_failure(job: object) -> None:
        host.failures += 1

    def record_history(job: object) -> None:
        host.history += 1

    return JobExecutor(
        host,
        write_log=write_log,
        write_failure=write_failure,
        record_history=record_history,
    )


def test_executor_runs_adapter_and_persists_success(tmp_path: Path) -> None:
    host = Host(tmp_path)
    job = _job(tmp_path)
    executor = _executor(host)

    def run(job: object, callbacks: JobCallbacks) -> RunOutcome:
        callbacks.progress("export", 50, "half")
        return RunOutcome(result={"ok": True})

    executor.run(job, run)
    assert job.status == "succeeded"
    assert job.result == {"ok": True}
    assert job.progress == 100
    assert host.persisted >= 2
    assert host.drained == 1


def test_executor_pauses_on_cancellation_when_pause_requested(tmp_path: Path) -> None:
    host = Host(tmp_path)
    job = _job(tmp_path)
    job.pause_requested = True
    executor = _executor(host)

    def run(job: object, callbacks: JobCallbacks) -> RunOutcome:
        raise JobCancelledError("pause")

    executor.run(job, run)
    assert job.status == "paused"
    assert job.error is None


def test_executor_marks_cancelled_and_writes_failure(tmp_path: Path) -> None:
    host = Host(tmp_path)
    job = _job(tmp_path)
    executor = _executor(host)

    def run(job: object, callbacks: JobCallbacks) -> RunOutcome:
        raise JobCancelledError("cancel")

    executor.run(
        job,
        run,
        JobRunPolicy(write_failure=True, cancel_error=True),
    )
    assert job.status == "cancelled"
    assert job.error is not None
    assert host.failures == 1


def test_executor_reports_step_progress_and_timeline_ready(tmp_path: Path) -> None:
    host = Host(tmp_path)
    job = _job(tmp_path)
    (tmp_path / "project_state.json").write_text("{}", encoding="utf-8")
    executor = _executor(host)

    leases: list[str] = []

    def run(job: object, callbacks: JobCallbacks) -> RunOutcome:
        callbacks.step_progress("transcribe", 42, "words")
        leases.append(job.lease_expires_at)  # type: ignore[attr-defined]
        callbacks.log("transcribe", "info", "done")
        return RunOutcome(result={"ok": True})

    executor.run(job, run)
    assert job.step_progress["transcribe"] == 42
    assert job.timeline_ready is True
    assert job.telemetry.lines == [("transcribe", "info", "done")]
    assert job.telemetry.updates == [("transcribe", 42, "words")]
    assert leases and leases[0]


def test_executor_waits_for_approval(tmp_path: Path) -> None:
    from videoflow.domain.errors import ApprovalRequiredError

    host = Host(tmp_path)
    job = _job(tmp_path)
    executor = _executor(host)

    def run(job: object, callbacks: JobCallbacks) -> RunOutcome:
        raise ApprovalRequiredError("gate", "Review", "Approve it")

    executor.run(job, run)
    assert job.status == "waiting_approval"
    assert job.error is not None
    assert host.persisted >= 2


def test_executor_schedules_retry_before_failing(tmp_path: Path) -> None:
    from videoflow.domain.errors import VideoFlowError

    host = Host(tmp_path)
    host.retry = True
    job = _job(tmp_path)
    executor = _executor(host)

    def run(job: object, callbacks: JobCallbacks) -> RunOutcome:
        raise VideoFlowError("temporary")

    executor.run(job, run)
    assert job.status == "queued"
    assert job.telemetry.failed == ["temporary"]
