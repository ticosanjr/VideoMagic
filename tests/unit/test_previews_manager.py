"""Browser preview rendering, filters, cancellation, and manager state."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.application import previews
from videoflow.domain.errors import JobCancelledError, StateNotReadyError
from videoflow.domain.state import ProjectState


def fake_job(tmp_path: Path, *, result: dict[str, object] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job-1",
        output=tmp_path / "out",
        result=result or {},
    )


class FakeAdapter:
    calls: list[tuple[Path, Path, dict[str, object]]] = []

    def __init__(self, cancel_event: object | None = None) -> None:
        self.cancel_event = cancel_event

    def transcode_preview(self, source: Path, target: Path, **kwargs: object) -> Path:
        self.calls.append((source, target, kwargs))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"preview")
        return target


def test_preview_paths_are_scoped_to_the_job(tmp_path: Path) -> None:
    job = fake_job(tmp_path)

    full, preview = previews.preview_paths(job)

    assert full == job.output / "preview" / "timeline-preview.mp4"
    assert preview == job.output / "preview" / "preview.mp4"


def test_fallback_prefers_mp4_artifacts_then_shorts(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"video")
    job = fake_job(tmp_path, result={"artifacts": {"a": clip, "b": "ignore.txt"}})
    assert previews._fallback_source(job) == clip

    short = tmp_path / "short.mp4"
    short.write_bytes(b"video")
    job = fake_job(tmp_path, result={"shorts": [{"path": short}]})
    assert previews._fallback_source(job) == short


def test_fallback_without_media_is_actionable(tmp_path: Path) -> None:
    job = fake_job(tmp_path, result={"artifacts": {"a": tmp_path / "missing.mp4"}})

    with pytest.raises(StateNotReadyError, match="no MP4 artifact"):
        previews._fallback_source(job)


def test_artifact_filters_are_loaded_and_bad_json_is_ignored(tmp_path: Path) -> None:
    job = fake_job(tmp_path)
    (job.output / "color").mkdir(parents=True)
    (job.output / "color" / "filters.json").write_text(
        '{"filters": ["eq=contrast=1.2", ""]}', encoding="utf-8"
    )
    (job.output / "audio").mkdir(parents=True)
    (job.output / "audio" / "master-filters.json").write_text(
        "not json", encoding="utf-8"
    )

    assert previews._video_filters(job) == ["eq=contrast=1.2"]
    assert previews._audio_filters(job) == []


def test_track_filters_follow_muted_and_solo_state(
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

    assert previews._track_filters(job) == ["volume=0"]
    assert previews._video_track_filters(job) == [
        "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill"
    ]

    monkeypatch.setattr(
        "videoflow.application.timeline_meta.load_meta",
        lambda _output: Meta({"video": Track(True, True), "audio": Track(False, False)}),
    )
    assert previews._track_filters(job) == []
    assert previews._video_track_filters(job) == []

    def fail(_output: Path) -> None:
        raise OSError("missing")

    monkeypatch.setattr("videoflow.application.timeline_meta.load_meta", fail)
    assert previews._track_filters(job) == []
    assert previews._video_track_filters(job) == []


def test_build_preview_renders_from_project_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = fake_job(tmp_path)
    job.output.mkdir(parents=True)
    (job.output / "project_state.json").write_text(
        ProjectState().model_dump_json(), encoding="utf-8"
    )
    (job.output / "titles.ass").write_text("[Script Info]", encoding="utf-8")
    seen: dict[str, object] = {}
    messages: list[tuple[int, str]] = []

    def fake_export(state: object, target: Path, **kwargs: object) -> Path:
        seen["state"] = state
        seen["target"] = target
        seen["kwargs"] = kwargs
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"full")
        return target

    monkeypatch.setattr(previews, "FFmpegAdapter", FakeAdapter)
    monkeypatch.setattr(previews, "export_mp4", fake_export)

    result = previews.build_preview(
        job, progress=lambda percent, message: messages.append((percent, message))
    )

    assert result == job.output / "preview" / "preview.mp4"
    target = seen["target"]
    assert isinstance(target, Path)
    assert target.parent == job.output / "preview"
    assert target.name.endswith(".part.mp4")
    kwargs = seen["kwargs"]
    assert isinstance(kwargs, dict)
    assert "ass_path" in kwargs
    assert kwargs["scale_height"] == previews.proxy_height()
    assert messages[0] == (5, "Reading project state")
    assert messages[-1] == (100, "Preview ready")
    assert result.read_bytes() == b"full"


def test_build_preview_falls_back_to_the_last_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"video")
    job = fake_job(tmp_path, result={"artifacts": {"video": clip}})
    monkeypatch.setattr(previews, "FFmpegAdapter", FakeAdapter)
    messages: list[tuple[int, str]] = []

    result = previews.build_preview(
        job, progress=lambda percent, message: messages.append((percent, message))
    )

    assert result.is_file()
    assert messages[0] == (20, "Using the last MP4 artifact")


def test_build_preview_honours_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = fake_job(tmp_path)
    monkeypatch.setattr(previews, "FFmpegAdapter", FakeAdapter)

    with pytest.raises(JobCancelledError):
        previews.build_preview(job, should_cancel=lambda: True)


def test_preview_manager_reuses_active_renders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeThread:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def start(self) -> None:
            return None

    monkeypatch.setattr(previews.threading, "Thread", FakeThread)
    manager = previews.PreviewManager()
    job = fake_job(tmp_path)

    first = manager.start(job)
    second = manager.start(job)

    assert first is second
    assert manager.get("job-1") is first
    assert manager.get("missing") is None


def test_preview_manager_work_marks_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    job = fake_job(tmp_path)
    manager = previews.PreviewManager()
    item = previews.PreviewState(job_id="job-1")

    def fake_build(job: object, **kwargs: object) -> Path:
        progress = kwargs["progress"]
        progress(40, "Rendering")
        return job.output / "preview" / "preview.mp4"  # type: ignore[attr-defined]

    monkeypatch.setattr(previews, "build_preview", fake_build)

    manager._work(job, item)

    assert item.status == "ready"
    assert item.percent == 100
    assert item.message == "Preview ready"
    assert item.finished_at


def test_preview_manager_work_marks_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = fake_job(tmp_path)
    manager = previews.PreviewManager()
    item = previews.PreviewState(job_id="job-1")

    def fail(*_args: object, **_kwargs: object) -> Path:
        raise RuntimeError("encoder missing")

    monkeypatch.setattr(previews, "build_preview", fail)

    manager._work(job, item)

    assert item.status == "failed"
    assert item.error == "encoder missing"
    assert item.message == "Preview failed"
    assert item.finished_at


def test_preview_manager_work_marks_cancelled_and_removes_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = fake_job(tmp_path)
    preview = job.output / "preview" / "preview.mp4"
    preview.parent.mkdir(parents=True)
    preview.write_bytes(b"partial")
    manager = previews.PreviewManager()
    item = previews.PreviewState(job_id="job-1", cancel_requested=True)

    def cancel(*_args: object, **_kwargs: object) -> Path:
        raise JobCancelledError("Preview cancelled")

    monkeypatch.setattr(previews, "build_preview", cancel)

    manager._work(job, item)

    assert item.status == "cancelled"
    assert item.message == "Cancelled"
    assert not preview.exists()


def test_preview_cancel_sets_the_event_only_while_active() -> None:
    manager = previews.PreviewManager()
    item = previews.PreviewState(job_id="job-1")
    manager._items["job-1"] = item

    cancelled = manager.cancel("job-1")

    assert cancelled is item
    assert item.cancel_requested is True
    assert item.cancel_event.is_set()

    item.status = "ready"
    finished = manager.cancel("job-1")
    assert finished is item
    assert item.cancel_event.is_set()
    assert manager.cancel("missing") is None


def test_preview_manifest_tracks_the_current_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = fake_job(tmp_path)
    job.output.mkdir(parents=True)
    state = ProjectState()
    state_path = job.output / "project_state.json"
    state_path.write_text(state.model_dump_json(), encoding="utf-8")
    preview = job.output / "preview" / "preview.mp4"

    def fake_build(job: object, **kwargs: object) -> Path:
        preview.parent.mkdir(parents=True, exist_ok=True)
        preview.write_bytes(b"preview")
        return preview

    monkeypatch.setattr(previews, "build_preview", fake_build)
    manager = previews.PreviewManager()
    item = previews.PreviewState(job_id="job-1")

    manager._work(job, item)

    assert item.status == "ready"
    assert item.revision == state.revision
    assert manager.is_ready(job) is True

    newer = state.model_copy(update={"revision": state.revision + 1})
    state_path.write_text(newer.model_dump_json(), encoding="utf-8")
    assert manager.is_ready(job) is False
