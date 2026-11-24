"""Jobs written by one MCP process are visible to another JobManager."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from videoflow.api.app import create_app
from videoflow.application import database
from videoflow.application.jobs import JobManager, track_mcp_job
from videoflow.mcp_server.guard import mcp_tool_guard


def test_track_mcp_job_is_visible_and_completes_across_managers(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    store = tmp_path / "jobs"
    JobManager(store_dir=store)
    second = JobManager(store_dir=store)

    tracker = track_mcp_job(
        "vf_decupage",
        project_id="paula-ep-10",
        source=str(tmp_path / "source.mp4"),
        output=str(tmp_path / "out"),
    )
    with tracker:
        running = second.list()
        assert [job.status for job in running] == ["running"]
        assert running[0].stage == "vf_decupage"
        assert running[0].options["origin"] == "mcp"
        assert running[0].options["pid"] == os.getpid()
        tracker.finish({"ok": True, "project_id": "paula-ep-10"})

    completed = second.list()
    assert completed[0].status == "succeeded"
    assert completed[0].progress == 100
    assert completed[0].result == {"ok": True, "project_id": "paula-ep-10"}


def test_mcp_tracker_marks_failure_on_exception(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    manager = JobManager(store_dir=tmp_path / "jobs")
    tracker = track_mcp_job("vf_scenes", project_id="p")
    with pytest.raises(RuntimeError, match="boom"), tracker:
        raise RuntimeError("boom")
    job = manager.list()[0]
    assert job.status == "failed"
    assert job.error is not None
    assert job.error["code"] == "internal_error"


def test_running_job_with_dead_pid_is_marked_interrupted(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    manager = JobManager(store_dir=tmp_path / "jobs")
    job_id = str(uuid4())
    database.upsert_job(
        job_id,
        {
            "job_id": job_id,
            "project_id": "p",
            "status": "running",
            "stage": "vf_run",
            "progress": 42,
            "message": "Running",
            "source": "",
            "output": "",
            "options": {"origin": "mcp", "pid": 2**31 - 1},
            "created_at": "2026-01-01T00:00:00Z",
        },
    )
    jobs = manager.list()
    dead = next(job for job in jobs if str(job.job_id) == job_id)
    assert dead.status == "failed"
    assert dead.error is not None
    assert dead.error["code"] == "worker_interrupted"


def test_guard_tracks_synchronous_tools(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))

    def vf_scenes(project_id: str) -> dict[str, object]:
        rows = database.list_jobs(project_id=project_id)
        assert any(row.get("status") == "running" for row in rows)
        return {"ok": True}

    result = mcp_tool_guard(vf_scenes)(project_id="cross-process")
    assert result["ok"] is True
    rows = database.list_jobs(project_id="cross-process")
    assert rows[0]["status"] == "succeeded"
    assert rows[0]["origin"] == "mcp"


def test_guard_does_not_duplicate_a_job_owned_tool(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))

    def vf_run(project_id: str) -> dict[str, object]:
        return {"ok": True}

    result = mcp_tool_guard(vf_run)(project_id="cross-process")
    assert result["ok"] is True
    assert database.list_jobs(project_id="cross-process") == []


def test_api_jobs_reads_a_running_mcp_tracker(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    tracker = track_mcp_job("vf_scenes", project_id="api-visible")
    with tracker:
        response = TestClient(create_app()).get("/api/v1/jobs")
        assert response.status_code == 200
        jobs = response.json()["jobs"]
        assert any(
            job["job_id"] == tracker.job_id and job["status"] == "running"
            for job in jobs
        )
        tracker.finish({"ok": True})
