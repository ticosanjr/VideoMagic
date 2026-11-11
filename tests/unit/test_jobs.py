import threading
import time
from pathlib import Path

import pytest

from tests.recipe_jobs import manager_with_runner, start_recipe
from videoflow.application.jobs import JobManager
from videoflow.domain.errors import (
    JobAlreadyRunningError,
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
    manager = manager_with_runner(fake_runner)
    job = start_recipe(manager, tmp_path / "in.mp4", tmp_path / "out")
    wait_for(job, manager)
    finished = manager.get(str(job.job_id))
    assert finished.status == "succeeded"
    assert finished.progress == 100
    assert finished.result == {
        "ok": True,
        "artifacts": {"resolve": str(tmp_path / "out" / "timeline.fcpxml")},
    }


def test_job_receives_runner_step_progress(tmp_path: Path) -> None:
    def runner(
        source: Path,
        output: Path,
        *,
        progress,
        step_progress,
        should_cancel,
        **kwargs,
    ):
        step_progress("transcribe", 42, "words")
        return {"ok": True}

    manager = manager_with_runner(runner)
    job = start_recipe(manager, tmp_path / "in.mp4", tmp_path / "out")
    wait_for(job, manager)
    finished = manager.get(str(job.job_id))
    assert finished.step_progress["transcribe"] == 42


def test_job_failure_is_recorded(tmp_path: Path) -> None:
    def failing(*args, **kwargs):
        raise VideoFlowError("boom")

    manager = manager_with_runner(failing)
    job = start_recipe(manager, tmp_path / "in.mp4", tmp_path / "out")
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

    manager = manager_with_runner(slow)
    job = start_recipe(manager, tmp_path / "in.mp4", tmp_path / "out")
    assert started.wait(2)
    manager.cancel(str(job.job_id))
    wait_for(job, manager)
    assert manager.get(str(job.job_id)).status == "cancelled"


def test_queue_limit(tmp_path: Path) -> None:
    blocker = threading.Event()

    def wait_runner(*args, **kwargs):
        blocker.wait(2)
        return {"ok": True}

    manager = manager_with_runner(wait_runner, max_active=1)
    start_recipe(manager, tmp_path / "a.mp4", tmp_path / "a")
    with pytest.raises(JobQueueFullError):
        start_recipe(manager, tmp_path / "b.mp4", tmp_path / "b")
    blocker.set()


def test_unknown_job(tmp_path: Path) -> None:
    manager = manager_with_runner(fake_runner)
    with pytest.raises(JobNotFoundError):
        manager.get("missing")
    assert manager.list() == []


def test_cancel_terminal_job_is_a_noop(tmp_path: Path) -> None:
    manager = manager_with_runner(fake_runner)
    job = start_recipe(manager, tmp_path / "in.mp4", tmp_path / "out")
    wait_for(job, manager)
    assert manager.cancel(str(job.job_id)).status == "succeeded"


def test_timeline_ready_is_visible_while_the_job_is_running(tmp_path: Path) -> None:
    ready = threading.Event()
    release = threading.Event()

    def runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        output.mkdir(parents=True, exist_ok=True)
        (output / "project_state.json").write_text("{}", encoding="utf-8")
        progress("timeline", 100, "Timeline ready")
        ready.set()
        release.wait(2)
        return {"ok": True}

    manager = manager_with_runner(runner)
    job = start_recipe(manager, tmp_path / "in.mp4", tmp_path / "out")
    assert ready.wait(2)
    assert manager.get(str(job.job_id)).timeline_ready is True
    release.set()
    wait_for(job, manager)


def test_removing_a_running_job_stops_it_and_does_not_reappear(tmp_path: Path) -> None:
    started = threading.Event()

    def runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        started.set()
        while not should_cancel():
            time.sleep(0.01)
        raise JobCancelledError("removed")

    store = tmp_path / "store"
    manager = manager_with_runner(runner, max_active=1, store_dir=store)
    job = start_recipe(manager, tmp_path / "in.mp4", tmp_path / "out")
    assert started.wait(2)
    manager.remove(str(job.job_id), force=True)
    with pytest.raises(JobNotFoundError):
        manager.get(str(job.job_id))
    time.sleep(0.15)
    assert not (store / f"{job.job_id}.json").exists()
    assert manager.list() == []


def test_removing_a_queued_job_drains_the_next_worker(tmp_path: Path) -> None:
    blocker = threading.Event()

    def runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        blocker.wait(3)
        return {"ok": True}

    manager = manager_with_runner(runner, max_active=1)
    first = start_recipe(manager, tmp_path / "a.mp4", tmp_path / "a")
    second = start_recipe(manager, tmp_path / "b.mp4", tmp_path / "b", queue=True)
    assert second.status == "queued"
    manager.remove(str(second.job_id), force=True)
    third = start_recipe(manager, tmp_path / "c.mp4", tmp_path / "c", queue=True)
    assert third.status == "queued"
    blocker.set()
    wait_for(first, manager)
    wait_for(third, manager)
    assert manager.get(str(third.job_id)).status == "succeeded"




def test_cancel_all_stops_running_and_queued_jobs(tmp_path: Path) -> None:
    started = threading.Event()

    def runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        started.set()
        while not should_cancel():
            time.sleep(0.01)
        raise JobCancelledError("stopped")

    manager = manager_with_runner(runner, max_active=1)
    first = start_recipe(manager, tmp_path / "a.mp4", tmp_path / "a")
    second = start_recipe(manager, tmp_path / "b.mp4", tmp_path / "b", queue=True)
    assert started.wait(2)
    manager.cancel_all(force=True)
    assert first.status == "cancelled"
    assert second.status == "cancelled"
    wait_for(first, manager)


def test_history_is_pruned(tmp_path: Path) -> None:
    manager = manager_with_runner(fake_runner, history=0)
    first = start_recipe(manager, tmp_path / "a.mp4", tmp_path / "a")
    wait_for(first, manager)
    second = start_recipe(manager, tmp_path / "b.mp4", tmp_path / "b")
    wait_for(second, manager)
    assert len(manager.list()) == 1








def test_idempotency_key_reuses_an_active_job(tmp_path: Path) -> None:
    release = threading.Event()

    def runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        release.wait(timeout=3.0)
        return {"ok": True}

    manager = manager_with_runner(runner)
    source = tmp_path / "source.mp4"
    output = tmp_path / "out"
    first = start_recipe(manager, source, output, idempotency_key="run-1", queue=True)
    second = start_recipe(manager, source, output, idempotency_key="run-1", queue=True)
    third = start_recipe(
        manager, source, tmp_path / "other", idempotency_key="run-2", queue=True
    )

    assert second.job_id == first.job_id
    assert third.job_id != first.job_id
    release.set()


def test_duplicate_source_and_output_is_rejected(tmp_path: Path) -> None:
    release = threading.Event()

    def runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        release.wait(timeout=3.0)
        return {"ok": True}

    manager = manager_with_runner(runner)
    source = tmp_path / "source.mp4"
    output = tmp_path / "out"
    first = start_recipe(manager, source, output)

    with pytest.raises(JobAlreadyRunningError):
        start_recipe(manager, source, output, queue=True)

    release.set()
    wait_for(first, manager)


def test_pause_and_unpause_a_queued_job(tmp_path: Path) -> None:
    release = threading.Event()

    def runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        release.wait(timeout=5.0)
        return {"ok": True}

    manager = manager_with_runner(runner, max_active=1)
    first = start_recipe(manager, tmp_path / "a.mp4", tmp_path / "out-a", {})
    second = start_recipe(manager, tmp_path / "b.mp4", tmp_path / "out-b", {}, queue=True)
    for _ in range(100):
        if second.status == "queued":
            break
        time.sleep(0.01)

    paused = manager.pause(str(second.job_id))
    assert paused.status == "paused"
    assert paused.message == "Paused"
    release.set()
    wait_for(first, manager)
    time.sleep(0.05)
    assert manager.get(str(second.job_id)).status == "paused"

    resumed = manager.unpause(str(second.job_id))
    assert resumed.status in {"queued", "running", "succeeded"}
    wait_for(resumed, manager)
    assert manager.get(str(second.job_id)).status == "succeeded"


def test_priority_is_stored_and_validated(tmp_path: Path) -> None:
    release = threading.Event()

    def runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        release.wait(timeout=5.0)
        return {"ok": True}

    manager = manager_with_runner(runner, max_active=1)
    first = start_recipe(manager, tmp_path / "a.mp4", tmp_path / "out-a", {})
    queued = start_recipe(manager, tmp_path / "b.mp4", tmp_path / "out-b", {}, queue=True)

    updated = manager.set_priority(str(queued.job_id), 7)

    assert updated.priority == 7
    release.set()
    wait_for(first, manager)


def test_failed_job_retries_with_backoff(tmp_path: Path) -> None:
    calls = {"count": 0}

    def runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise VideoFlowError("transient")
        return {"ok": True}

    manager = manager_with_runner(runner)
    job = start_recipe(manager, 
        tmp_path / "a.mp4",
        tmp_path / "out",
        {"max_attempts": 2, "retry_backoff_seconds": 0.1},
    )
    deadline = time.time() + 5
    while time.time() < deadline:
        current = manager.get(str(job.job_id))
        if current.status == "succeeded":
            break
        time.sleep(0.05)

    assert calls["count"] == 2
    assert manager.get(str(job.job_id)).status == "succeeded"
    assert manager.get(str(job.job_id)).attempts == 1
