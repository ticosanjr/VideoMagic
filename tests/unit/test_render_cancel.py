"""Cancellation of background renders and previews, including partial cleanup."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from videoflow.application import previews, render_queue
from videoflow.application.previews import PreviewManager, preview_paths
from videoflow.application.render_queue import RenderQueue
from videoflow.domain.state import ProjectState


def wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not reached")


def build_job(tmp_path: Path) -> Any:
    output = tmp_path / "output"
    output.mkdir()
    state = ProjectState()
    (output / "project_state.json").write_text(
        state.model_dump_json(), encoding="utf-8"
    )
    return SimpleNamespace(job_id="job-1", output=output, result={})


def blocking_export(destination: Path):
    def fake_export(state, target, *, adapter, **kwargs):
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"partial")
        wait_until(lambda: adapter.cancel_event.is_set())

    return fake_export


def test_render_cancel_stops_and_removes_the_partial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    job = build_job(tmp_path)
    destination = tmp_path / "output" / "render" / "timeline.mp4"
    monkeypatch.setattr(render_queue, "export_mp4", blocking_export(destination))
    queue = RenderQueue()

    item = queue.start(job)
    wait_until(lambda: item.status == "rendering")
    queue.cancel(str(job.job_id))
    wait_until(lambda: item.status == "cancelled")

    assert item.cancel_requested is True
    assert not destination.exists()


def test_render_cancel_before_the_slot_prevents_the_export(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    job = build_job(tmp_path)
    calls: list[Path] = []

    def fake_export(state, target, *, adapter, **kwargs):
        calls.append(Path(target))

    monkeypatch.setattr(render_queue, "export_mp4", fake_export)
    queue = RenderQueue()
    queue._slot.acquire()  # hold the single render slot so the job stays queued
    item = queue.start(job)
    wait_until(lambda: item.status == "queued")
    queue.cancel(str(job.job_id))
    queue._slot.release()
    wait_until(lambda: item.status == "cancelled")

    assert calls == []


def test_preview_cancel_removes_the_partial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    job = build_job(tmp_path)
    full, preview = preview_paths(job)
    monkeypatch.setattr(previews, "export_mp4", blocking_export(full))
    manager = PreviewManager()

    item = manager.start(job)
    wait_until(lambda: item.status == "rendering")
    manager.cancel(str(job.job_id))
    wait_until(lambda: item.status == "cancelled")

    assert not preview.exists()
