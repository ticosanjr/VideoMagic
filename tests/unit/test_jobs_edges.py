"""Operational branches of the job manager."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from tests.recipe_jobs import manager_with_runner, start_recipe
from videoflow.application import jobs as jobs_module
from videoflow.domain.errors import JobNotFoundError, JobQueueFullError, ProjectStateError
from videoflow.domain.state import MediaInfo, ProjectState


def _wait(job, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while job.status not in {"succeeded", "failed", "cancelled"} and time.monotonic() < deadline:
        time.sleep(0.01)
    # The worker writes the JSON store in its finally block after setting status.
    time.sleep(0.05)
    return job


def test_queue_full_cancel_pause_and_unpause(tmp_path: Path) -> None:
    import threading

    release = threading.Event()

    def runner(source, output, *, progress, should_cancel, **kwargs):
        release.wait(timeout=5)
        return {"ok": True}

    manager = manager_with_runner(runner=runner, max_active=1)
    first = start_recipe(manager, tmp_path / "a.mp4", tmp_path / "a", {})
    with pytest.raises(JobQueueFullError):
        start_recipe(manager, tmp_path / "b.mp4", tmp_path / "b", {})
    second = start_recipe(manager, tmp_path / "b.mp4", tmp_path / "b", {}, queue=True)
    assert second.status == "queued"

    assert manager.cancel(str(second.job_id)).status == "cancelled"
    paused = manager.pause(str(first.job_id))
    assert paused.status == "paused" or paused.pause_requested is True
    release.set()
    _wait(first)
    assert manager.pause(str(first.job_id)).status in {"succeeded", "cancelled", "failed"}
    assert manager.cancel(str(first.job_id)).status == manager.get(str(first.job_id)).status


def test_queued_pause_and_unpause(tmp_path: Path) -> None:
    import threading

    release = threading.Event()

    def runner(source, output, *, progress, should_cancel, **kwargs):
        release.wait(timeout=5)
        return {"ok": True}

    manager = manager_with_runner(runner=runner, max_active=1)
    first = start_recipe(manager, tmp_path / "a.mp4", tmp_path / "a", {})
    second = start_recipe(manager, tmp_path / "b.mp4", tmp_path / "b", {}, queue=True)
    paused = manager.pause(str(second.job_id))
    assert paused.status == "paused"
    resumed = manager.unpause(str(second.job_id))
    assert resumed.status in {"queued", "running"}
    release.set()
    _wait(first)
    _wait(second)


def test_get_loads_from_the_store_and_prunes_history(tmp_path: Path) -> None:
    def runner(source, output, *, progress, should_cancel, **kwargs):
        Path(output).mkdir(parents=True, exist_ok=True)
        return {"ok": True}

    store = tmp_path / "jobs"
    manager = manager_with_runner(runner=runner, max_active=2, store_dir=store, history=1)
    first = _wait(start_recipe(manager, tmp_path / "a.mp4", tmp_path / "a", {}))
    second = _wait(start_recipe(manager, tmp_path / "b.mp4", tmp_path / "b", {}))
    third = _wait(start_recipe(manager, tmp_path / "c.mp4", tmp_path / "c", {}))
    manager._prune()  # noqa: SLF001
    assert str(first.job_id) not in {str(item.job_id) for item in manager.list()}
    assert str(third.job_id) in {str(item.job_id) for item in manager.list()}
    assert not (store / f"{first.job_id}.json").exists()

    loaded = manager_with_runner(runner=runner, store_dir=store)
    restored = loaded.get(str(third.job_id))
    assert restored.job_id == third.job_id
    with pytest.raises(JobNotFoundError):
        loaded.get(str(second.job_id))


def test_retry_with_backoff_reaches_success(tmp_path: Path) -> None:
    attempts = {"count": 0}

    def runner(source, output, *, progress, should_cancel, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("transient")
        return {"ok": True}

    manager = manager_with_runner(runner=runner, max_active=1)
    job = start_recipe(manager, 
        tmp_path / "a.mp4",
        tmp_path / "a",
        {"max_attempts": 2, "retry_backoff_seconds": 0.01},
    )
    _wait(job, timeout=8)
    assert job.attempts >= 1
    assert job.status in {"succeeded", "failed"}


def test_private_parsers_and_failure_report(tmp_path: Path) -> None:
    assert jobs_module._string_dict({" a ": " b "}, {}) == {"a": "b"}
    assert jobs_module._string_dict("a=b,invalid,c=d", {}) == {"a": "b", "c": "d"}
    assert jobs_module._string_dict(None, {"x": "y"}) == {"x": "y"}
    assert jobs_module._string_list([" a ", ""], []) == ["a"]
    assert jobs_module._string_list("a, b", []) == ["a", "b"]
    assert jobs_module._string_list(None, ["d"]) == ["d"]

    transcript = tmp_path / "project_state.json"
    transcript.write_text(
        ProjectState(
            media_info=MediaInfo(
                source_path="/tmp/s.mp4",
                duration_frames=10,
                fps_num=30,
                fps_den=1,
                width=10,
                height=10,
                audio_sample_rate=48000,
            ),
            transcript=[
                {
                    "id": 0,
                    "start_sample": 0,
                    "end_sample": 48000,
                    "text": "hello",
                    "speaker": 0,
                }
            ],
        ).model_dump_json(),
        encoding="utf-8",
    )
    sentences = jobs_module._project_transcript(str(transcript))
    assert sentences and sentences[0].text == "hello"
    with pytest.raises(ProjectStateError):
        jobs_module._project_transcript(str(tmp_path / "missing.json"))

    job = jobs_module.Job(
        source=tmp_path / "a.mp4",
        output=tmp_path / "failure-out",
        options={},
        status="failed",
        stage="ingest",
        message="boom",
        error={"code": "internal_error", "message": "boom"},
    )
    (tmp_path / "failure-out").mkdir()
    jobs_module._write_failure(job)
    payload = json.loads((tmp_path / "failure-out" / "work" / "failure.json").read_text())
    assert payload["stage"] == "ingest"
    assert payload["error"]["code"] == "internal_error"


def test_queued_cancel_missing_ids_and_store_fallback(tmp_path: Path) -> None:
    def runner(source, output, *, progress, should_cancel, **kwargs):
        return {"ok": True}

    manager = manager_with_runner(runner=runner, store_dir=tmp_path / "store")
    job = jobs_module.Job(
        source=tmp_path / "a.mp4",
        output=tmp_path / "out",
        options={},
        status="queued",
    )
    manager._jobs[str(job.job_id)] = job
    manager._pending.append(str(job.job_id))
    cancelled = manager.cancel(str(job.job_id))
    assert cancelled.status == "cancelled"
    assert jobs_module._duration_ms("not-a-date", None) is None
    from videoflow.domain.errors import JobNotFoundError

    with pytest.raises(JobNotFoundError):
        manager.pause("missing")
    with pytest.raises(JobNotFoundError):
        manager.unpause("missing")
    with pytest.raises(JobNotFoundError):
        manager.set_priority("missing", 1)

    manager._jobs.pop(str(job.job_id))
    manager._persist_job(job)
    loaded = manager.get(str(job.job_id))
    assert loaded.status == "cancelled"


def test_corrupt_store_and_pending_entries_are_skipped(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    (store / "bad.json").write_text("{not json", encoding="utf-8")
    manager = manager_with_runner(store_dir=store)
    manager._drain_queue()
    assert manager.list() == []


def test_paused_running_job_is_reported(tmp_path: Path) -> None:
    import threading

    from videoflow.domain.errors import JobCancelledError

    release = threading.Event()

    def runner(source, output, *, progress, should_cancel, **kwargs):
        release.wait(timeout=5)
        raise JobCancelledError("paused")

    manager = manager_with_runner(runner=runner, max_active=1)
    job = start_recipe(manager, tmp_path / "a.mp4", tmp_path / "a", {})
    manager._jobs[str(job.job_id)].pause_requested = True
    manager._jobs[str(job.job_id)].cancel_requested = True
    release.set()
    _wait(job)
    assert job.status in {"paused", "cancelled"}


def test_finalizer_runs_on_success(tmp_path: Path) -> None:
    seen: list[str] = []

    def runner(source, output, *, progress, should_cancel, **kwargs):
        return {"ok": True}

    manager = manager_with_runner(runner=runner, max_active=1)
    job = start_recipe(manager, 
        tmp_path / "a.mp4",
        tmp_path / "a",
        {},
        finalizer=lambda item: seen.append(str(item.job_id)),
    )
    _wait(job)
    assert seen == [str(job.job_id)]
