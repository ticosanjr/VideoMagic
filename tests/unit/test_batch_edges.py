"""Batch manager edges: filtering, cancellation, queue pressure, and pruning."""

from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

import pytest

from tests.unit.test_batch import FakeJob, FakeJobs, wait_batch
from videoflow.domain.errors import BatchError, JobQueueFullError
from videoflow.engine.batch import Batch, BatchItem, BatchManager

RECIPE = {"id": "batch", "name": "Batch", "steps": [{"id": "ingest", "type": "ingest"}]}


def make_source(tmp_path: Path, *names: str) -> Path:
    source = tmp_path / "in"
    source.mkdir(exist_ok=True)
    for name in names:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"media")
    return source


def test_start_rejects_a_non_directory(tmp_path: Path) -> None:
    file = tmp_path / "file.mp4"
    file.write_bytes(b"x")

    with pytest.raises(BatchError, match="not a directory"):
        BatchManager(FakeJobs()).start(file, tmp_path / "out", RECIPE)


def test_recursive_and_extension_filters(tmp_path: Path) -> None:
    source = make_source(tmp_path, "a.mp4", "nested/b.MOV", "c.txt")

    manager = BatchManager(FakeJobs())
    batch = manager.start(
        source,
        tmp_path / "out",
        RECIPE,
        recursive=True,
        extensions=["mp4", ".mov"],
        resume=False,
    )

    assert batch.total == 2
    wait_batch(manager, str(batch.batch_id))


def test_get_reads_corrupt_and_missing_store_entries(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    (store / "bad.json").write_text("not json", encoding="utf-8")
    manager = BatchManager(FakeJobs(), store_dir=store)

    with pytest.raises(BatchError, match="Unknown batch"):
        manager.get("bad")
    with pytest.raises(BatchError, match="Unknown batch"):
        manager.get(str(uuid4()))


def test_list_is_paginated(tmp_path: Path) -> None:
    manager = BatchManager(FakeJobs())
    source = make_source(tmp_path, "a.mp4")
    first = manager.start(source, tmp_path / "out", RECIPE, resume=False)
    second = manager.start(source, tmp_path / "out", RECIPE, resume=False)
    wait_batch(manager, str(first.batch_id))
    wait_batch(manager, str(second.batch_id))

    assert len(manager.list()) == 2
    assert len(manager.list(limit=1)) == 1
    assert len(manager.list(offset=1)) == 1
    assert manager.list(limit=0) == []


def test_cancel_handles_unknown_terminal_and_active_batches(tmp_path: Path) -> None:
    jobs = FakeJobs()
    manager = BatchManager(jobs)
    source = make_source(tmp_path, "a.mp4")
    batch = manager.start(source, tmp_path / "out", RECIPE, resume=False)
    wait_batch(manager, str(batch.batch_id))

    assert manager.cancel(str(batch.batch_id)).status == "succeeded"
    with pytest.raises(BatchError, match="Unknown batch"):
        manager.cancel("missing")

    active = Batch(
        source_dir=source,
        output_root=tmp_path / "out",
        recipe_id="batch",
        recipe=RECIPE,
        items=[BatchItem(source=source / "a.mp4", output=tmp_path / "out" / "a")],
        status="running",
        current_job_id="job-1",
    )
    manager._batches[str(active.batch_id)] = active
    jobs.jobs["job-1"] = FakeJob()
    cancelled = manager.cancel(str(active.batch_id))

    assert cancelled.cancel_requested is True
    assert cancelled.message == "Cancellation requested"


def test_queue_pressure_retries_until_a_slot_opens(tmp_path: Path) -> None:
    class BusyOnce(FakeJobs):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def start(self, *args: object, **kwargs: object) -> FakeJob:
            self.calls += 1
            if self.calls == 1:
                raise JobQueueFullError("busy")
            return super().start(*args, **kwargs)  # type: ignore[arg-type]

    jobs = BusyOnce()
    manager = BatchManager(jobs)
    batch = manager.start(make_source(tmp_path, "a.mp4"), tmp_path / "out", RECIPE)

    finished = wait_batch(manager, str(batch.batch_id))

    assert finished.status == "succeeded"
    assert jobs.calls == 2


def test_cancellation_stops_a_running_job(tmp_path: Path) -> None:
    class SlowJobs(FakeJobs):
        def start(self, *args: object, **kwargs: object) -> FakeJob:
            job = FakeJob()
            job.status = "running"
            self.jobs[str(job.job_id)] = job
            self.started.append((Path(str(args[0])), Path(str(args[1])), {}))
            return job

        def cancel(self, job_id: str) -> FakeJob:
            self.jobs[job_id].status = "cancelled"
            return self.jobs[job_id]

    jobs = SlowJobs()
    manager = BatchManager(jobs)
    batch = manager.start(make_source(tmp_path, "a.mp4"), tmp_path / "out", RECIPE, resume=False)

    deadline = time.time() + 5
    while time.time() < deadline and jobs.started == []:
        time.sleep(0.01)
    manager.cancel(str(batch.batch_id))
    finished = wait_batch(manager, str(batch.batch_id))

    assert finished.status == "cancelled"
    assert finished.items[0].status == "cancelled"


def test_history_prunes_old_finished_batches(tmp_path: Path) -> None:
    store = tmp_path / "store"
    manager = BatchManager(FakeJobs(), history=1, store_dir=store)
    source = make_source(tmp_path, "a.mp4")
    oldest = Batch(
        source_dir=source,
        output_root=tmp_path / "out",
        recipe_id="batch",
        recipe=RECIPE,
        items=[],
        status="succeeded",
        finished_at="2020-01-01T00:00:00+00:00",
    )
    newest = Batch(
        source_dir=source,
        output_root=tmp_path / "out",
        recipe_id="batch",
        recipe=RECIPE,
        items=[],
        status="succeeded",
        finished_at="2021-01-01T00:00:00+00:00",
    )
    manager._batches[str(oldest.batch_id)] = oldest
    manager._batches[str(newest.batch_id)] = newest
    store.mkdir(parents=True, exist_ok=True)
    for item in (oldest, newest):
        (store / f"{item.batch_id}.json").write_text("{}", encoding="utf-8")

    new = manager.start(source, tmp_path / "out", RECIPE, resume=False)

    assert str(oldest.batch_id) not in manager._batches
    assert str(newest.batch_id) in manager._batches
    assert not (store / f"{oldest.batch_id}.json").exists()
    wait_batch(manager, str(new.batch_id))


def test_persist_survives_database_and_disk_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = BatchManager(FakeJobs(), store_dir=tmp_path / "store")
    batch = Batch(
        source_dir=tmp_path,
        output_root=tmp_path / "out",
        recipe_id="batch",
        recipe=RECIPE,
        items=[],
    )

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("videoflow.application.database.upsert_batch", fail)
    monkeypatch.setattr(Path, "write_text", fail)

    manager._persist(batch)
