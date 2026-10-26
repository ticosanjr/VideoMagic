"""Background render queue: caching, fallbacks, cancellation, and filters."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.application import render_queue
from videoflow.domain.errors import ExportError
from videoflow.domain.state import ProjectState
from videoflow.exporters.incremental import NotEligible


def fake_job(tmp_path: Path, *, result: dict[str, object] | None = None) -> SimpleNamespace:
    return SimpleNamespace(job_id="job-1", output=tmp_path / "out", result=result or {})


class FakeAdapter:
    def __init__(self, cancel_event: object | None = None) -> None:
        self.cancel_event = cancel_event


def write_state(job: SimpleNamespace) -> Path:
    job.output.mkdir(parents=True, exist_ok=True)
    path = job.output / "project_state.json"
    path.write_text(ProjectState().model_dump_json(), encoding="utf-8")
    return path


def test_output_path_and_state_serialisation(tmp_path: Path) -> None:
    job = fake_job(tmp_path)
    queue = render_queue.RenderQueue()

    assert queue.output_path(job) == job.output / "render" / "timeline.mp4"
    state = render_queue.RenderState(job_id="job-1")
    assert state.to_dict()["status"] == "queued"
    assert state.to_dict()["cancel_requested"] is False


def test_start_reuses_an_active_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeThread:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def start(self) -> None:
            return None

    monkeypatch.setattr(render_queue.threading, "Thread", FakeThread)
    queue = render_queue.RenderQueue()
    job = fake_job(tmp_path)

    assert queue.start(job) is queue.start(job)
    assert queue.get("job-1") is not None
    assert queue.get("missing") is None


def test_work_fails_without_project_state(tmp_path: Path) -> None:
    job = fake_job(tmp_path)
    item = render_queue.RenderState(job_id="job-1")

    render_queue.RenderQueue()._work(job, item)

    assert item.status == "failed"
    assert "project_state.json" in item.error
    assert item.finished_at


def test_work_renders_incrementally_when_eligible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = fake_job(tmp_path)
    write_state(job)
    item = render_queue.RenderState(job_id="job-1")
    monkeypatch.setattr(render_queue, "FFmpegAdapter", FakeAdapter)
    seen: dict[str, object] = {}

    def fake_incremental(state: object, target: Path, **kwargs: object) -> Path:
        seen["state"] = state
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"mp4")
        kwargs["progress"](50)
        return target

    monkeypatch.setattr(render_queue, "export_mp4_incremental", fake_incremental)
    monkeypatch.setattr(render_queue, "export_mp4", lambda *a, **k: None)

    render_queue.RenderQueue()._work(job, item)

    assert item.status == "ready"
    assert item.percent == 100
    assert seen["state"] is not None
    manifest = json.loads(
        (job.output / "render" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["source"].endswith("project_state.json")


def test_work_falls_back_when_incremental_is_not_eligible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = fake_job(tmp_path)
    write_state(job)
    item = render_queue.RenderState(job_id="job-1")
    monkeypatch.setattr(render_queue, "FFmpegAdapter", FakeAdapter)
    calls: list[str] = []

    def not_eligible(*_args: object, **_kwargs: object) -> Path:
        raise NotEligible("different encoder settings")

    def fake_export(_state: object, target: Path, **kwargs: object) -> Path:
        calls.append("full")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"mp4")
        kwargs["progress"](75)
        return target

    monkeypatch.setattr(render_queue, "export_mp4_incremental", not_eligible)
    monkeypatch.setattr(render_queue, "export_mp4", fake_export)

    render_queue.RenderQueue()._work(job, item)

    assert calls == ["full"]
    assert item.status == "ready"


def test_work_reuses_a_matching_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = fake_job(tmp_path)
    state_path = write_state(job)
    destination = job.output / "render" / "timeline.mp4"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"cached")
    filters: list[str] = []
    key = render_queue.hashlib.sha256(
        state_path.read_bytes()
        + json.dumps(filters).encode("utf-8")
        + b"0"
    ).hexdigest()
    (destination.parent / "manifest.json").write_text(
        json.dumps({"key": key}), encoding="utf-8"
    )
    item = render_queue.RenderState(job_id="job-1")
    monkeypatch.setattr(render_queue, "FFmpegAdapter", FakeAdapter)
    monkeypatch.setattr(
        render_queue,
        "export_mp4_incremental",
        lambda *a, **k: pytest.fail("should not render"),
    )

    render_queue.RenderQueue()._work(job, item)

    assert item.status == "ready"
    assert item.message == "Render ready (cached)"


def test_work_cancels_before_encoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = fake_job(tmp_path)
    write_state(job)
    item = render_queue.RenderState(job_id="job-1", cancel_requested=True)
    monkeypatch.setattr(render_queue, "FFmpegAdapter", FakeAdapter)

    render_queue.RenderQueue()._work(job, item)

    assert item.status == "cancelled"
    assert item.message == "Cancelled"


def test_work_removes_output_when_cancelled_during_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = fake_job(tmp_path)
    write_state(job)
    item = render_queue.RenderState(job_id="job-1")
    monkeypatch.setattr(render_queue, "FFmpegAdapter", FakeAdapter)

    def cancel_after_export(_state: object, target: Path, **_kwargs: object) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"partial")
        item.cancel_requested = True
        return target

    monkeypatch.setattr(
        render_queue,
        "export_mp4_incremental",
        lambda *a, **k: (_ for _ in ()).throw(NotEligible("no")),
    )
    monkeypatch.setattr(render_queue, "export_mp4", cancel_after_export)

    render_queue.RenderQueue()._work(job, item)

    assert item.status == "cancelled"
    assert not (job.output / "render" / "timeline.mp4").exists()


def test_work_reports_export_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = fake_job(tmp_path)
    write_state(job)
    item = render_queue.RenderState(job_id="job-1")
    monkeypatch.setattr(render_queue, "FFmpegAdapter", FakeAdapter)
    monkeypatch.setattr(
        render_queue,
        "export_mp4_incremental",
        lambda *a, **k: (_ for _ in ()).throw(NotEligible("no")),
    )

    def fail(*_args: object, **_kwargs: object) -> Path:
        raise ExportError("encoder crashed")

    monkeypatch.setattr(render_queue, "export_mp4", fail)

    render_queue.RenderQueue()._work(job, item)

    assert item.status == "failed"
    assert item.error == "encoder crashed"


def test_filter_files_are_read_and_bad_json_ignored(tmp_path: Path) -> None:
    assert render_queue._filters(tmp_path / "missing.json") == []

    path = tmp_path / "filters.json"
    path.write_text('{"filters": ["eq=contrast=1.1", ""]}', encoding="utf-8")
    assert render_queue._filters(path) == ["eq=contrast=1.1"]

    path.write_text("not json", encoding="utf-8")
    assert render_queue._filters(path) == []


def test_track_filters_translate_mute_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = fake_job(tmp_path)

    class Track:
        def __init__(self, muted: bool, solo: bool) -> None:
            self.muted = muted
            self.solo = solo

    class Meta:
        def __init__(self, tracks: dict[str, Track]) -> None:
            self.tracks = tracks

    monkeypatch.setattr(
        "videoflow.application.timeline_meta.load_meta",
        lambda _output: Meta({"video": Track(True, False), "audio": Track(True, False)}),
    )
    assert render_queue._track_filters(job) == ["volume=0"]
    assert render_queue._video_track_filters(job) == [
        "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill"
    ]

    monkeypatch.setattr(
        "videoflow.application.timeline_meta.load_meta",
        lambda _output: Meta({"video": Track(False, False), "audio": Track(True, True)}),
    )
    assert render_queue._track_filters(job) == []
    assert render_queue._video_track_filters(job) == []

    def fail(_output: Path) -> None:
        raise OSError("missing")

    monkeypatch.setattr("videoflow.application.timeline_meta.load_meta", fail)
    assert render_queue._track_filters(job) == []
    assert render_queue._video_track_filters(job) == []


def test_cancel_only_marks_active_renders() -> None:
    queue = render_queue.RenderQueue()
    item = render_queue.RenderState(job_id="job-1")
    queue._items["job-1"] = item

    assert queue.cancel("job-1") is item
    assert item.cancel_requested is True
    assert item.cancel_event.is_set()

    item.status = "ready"
    assert queue.cancel("job-1") is item
    assert queue.cancel("missing") is None
