from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from videoflow.api.app import create_app
from videoflow.domain.errors import BatchError
from videoflow.engine.batch import BatchManager


class FakeJob:
    def __init__(self) -> None:
        self.job_id = uuid4()
        self.status = "succeeded"
        self.message = "Finished"


class FakeJobs:
    def __init__(self) -> None:
        self.started: list[tuple[Path, Path, dict]] = []
        self.jobs: dict[str, FakeJob] = {}

    def start(self, source, output, options=None, **_kwargs):
        job = FakeJob()
        self.started.append((Path(source), Path(output), dict(options or {})))
        self.jobs[str(job.job_id)] = job
        return job

    def get(self, job_id: str) -> FakeJob:
        return self.jobs[job_id]

    def cancel(self, job_id: str) -> FakeJob:
        return self.jobs[job_id]


def wait_batch(manager: BatchManager, batch_id: str):
    for _ in range(200):
        batch = manager.get(batch_id)
        if batch.status in {"succeeded", "failed", "cancelled"}:
            return batch
        time.sleep(0.01)
    raise AssertionError("batch did not finish")


def test_batch_manager_processes_a_folder(tmp_path: Path) -> None:
    source = tmp_path / "in"
    source.mkdir()
    (source / "a.mp4").write_bytes(b"a")
    (source / "b.mov").write_bytes(b"b")
    (source / "ignore.txt").write_text("nope")
    jobs = FakeJobs()
    manager = BatchManager(jobs)  # type: ignore[arg-type]
    batch = manager.start(
        source,
        tmp_path / "out",
        {"id": "batch", "name": "Batch", "steps": [{"id": "ingest", "type": "ingest"}]},
        recipe_id="batch",
    )
    finished = wait_batch(manager, str(batch.batch_id))
    assert finished.status == "succeeded"
    assert finished.total == 2
    assert finished.completed == 2
    assert len(jobs.started) == 2
    assert all(options["mode"] == "recipe" for _, _, options in jobs.started)


def test_batch_manager_rejects_an_empty_folder(tmp_path: Path) -> None:
    source = tmp_path / "in"
    source.mkdir()
    (source / "readme.txt").write_text("nope")
    manager = BatchManager(FakeJobs())  # type: ignore[arg-type]
    with pytest.raises(BatchError, match="No media files"):
        manager.start(
            source,
            tmp_path / "out",
            {"id": "batch", "name": "Batch", "steps": [{"id": "ingest", "type": "ingest"}]},
        )


def test_batch_api_returns_a_batch(tmp_path: Path) -> None:
    home = tmp_path / "videoflow-home"
    source = home / "in"
    source.mkdir(parents=True)
    (source / "a.mp4").write_bytes(b"a")
    jobs = FakeJobs()
    client = TestClient(create_app(jobs=jobs))  # type: ignore[arg-type]
    response = client.post(
        "/api/v1/batches",
        json={
            "source_dir": str(source),
            "output_root": str(home / "out"),
            "recipe": {
                "id": "batch",
                "name": "Batch",
                "steps": [{"id": "ingest", "type": "ingest"}],
            },
        },
    )
    assert response.status_code == 202
    batch_id = response.json()["batch"]["batch_id"]
    for _ in range(200):
        current = client.get(f"/api/v1/batches/{batch_id}")
        assert current.status_code == 200
        if current.json()["batch"]["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.01)
    assert current.json()["batch"]["status"] == "succeeded"
