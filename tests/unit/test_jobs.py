import threading
import time
from pathlib import Path

import pytest

from videoflow.application.jobs import JobManager
from videoflow.domain.errors import (
    JobCancelledError,
    JobNotFoundError,
    JobQueueFullError,
    VideoFlowError,
)


def wait_for(job, manager: JobManager, timeout: float = 3.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if manager.get(str(job.job_id)).status in {"succeeded", "failed", "cancelled"}:
            return
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def fake_runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
    progress("probe", 5, "probe")
    progress("export", 80, "export")
    return {"ok": True, "artifacts": {"resolve": str(output / "timeline.fcpxml")}}


def test_job_completes_and_reports_progress(tmp_path: Path) -> None:
    manager = JobManager(fake_runner)
    job = manager.start(tmp_path / "in.mp4", tmp_path / "out")
    wait_for(job, manager)
    finished = manager.get(str(job.job_id))
    assert finished.status == "succeeded"
    assert finished.progress == 100
    assert finished.result == {
        "ok": True,
        "artifacts": {"resolve": str(tmp_path / "out" / "timeline.fcpxml")},
    }


def test_job_failure_is_recorded(tmp_path: Path) -> None:
    def failing(*args, **kwargs):
        raise VideoFlowError("boom")

    manager = JobManager(failing)
    job = manager.start(tmp_path / "in.mp4", tmp_path / "out")
    wait_for(job, manager)
    finished = manager.get(str(job.job_id))
    assert finished.status == "failed"
    assert finished.error == {
        "ok": False,
        "code": "videoflow_error",
        "message": "boom",
    }


def test_job_can_be_cancelled(tmp_path: Path) -> None:
    started = threading.Event()

    def slow(*args, **kwargs):
        started.set()
        while True:
            if kwargs["should_cancel"]():
                raise JobCancelledError("stopped")
            time.sleep(0.01)

    manager = JobManager(slow)
    job = manager.start(tmp_path / "in.mp4", tmp_path / "out")
    assert started.wait(2)
    manager.cancel(str(job.job_id))
    wait_for(job, manager)
    assert manager.get(str(job.job_id)).status == "cancelled"


def test_queue_limit(tmp_path: Path) -> None:
    blocker = threading.Event()

    def wait_runner(*args, **kwargs):
        blocker.wait(2)
        return {"ok": True}

    manager = JobManager(wait_runner, max_active=1)
    manager.start(tmp_path / "a.mp4", tmp_path / "a")
    with pytest.raises(JobQueueFullError):
        manager.start(tmp_path / "b.mp4", tmp_path / "b")
    blocker.set()


def test_unknown_job(tmp_path: Path) -> None:
    manager = JobManager(fake_runner)
    with pytest.raises(JobNotFoundError):
        manager.get("missing")
    assert manager.list() == []


def test_cancel_terminal_job_is_a_noop(tmp_path: Path) -> None:
    manager = JobManager(fake_runner)
    job = manager.start(tmp_path / "in.mp4", tmp_path / "out")
    wait_for(job, manager)
    assert manager.cancel(str(job.job_id)).status == "succeeded"


def test_history_is_pruned(tmp_path: Path) -> None:
    manager = JobManager(fake_runner, history=0)
    first = manager.start(tmp_path / "a.mp4", tmp_path / "a")
    wait_for(first, manager)
    second = manager.start(tmp_path / "b.mp4", tmp_path / "b")
    wait_for(second, manager)
    assert len(manager.list()) == 1
