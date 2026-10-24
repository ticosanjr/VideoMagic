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


def test_job_forwards_vad_options(tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        seen.update(kwargs)
        progress("done", 100, "done")
        return {"ok": True}

    manager = JobManager(runner)
    job = manager.start(
        tmp_path / "in.mp4",
        tmp_path / "out",
        {
            "vad_engine": "silero",
            "speech_threshold": 0.65,
            "speech_pad_before_ms": 40,
            "speech_pad_after_ms": 50,
        },
    )
    wait_for(job, manager)
    assert seen["vad_engine"] == "silero"
    assert seen["speech_threshold"] == 0.65
    assert seen["speech_pad_before_ms"] == 40
    assert seen["speech_pad_after_ms"] == 50


def test_job_forwards_faster_whisper_options(tmp_path: Path) -> None:
    from videoflow.domain.config import TranscribeConfig

    seen: dict[str, object] = {}

    def runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        seen.update(kwargs)
        progress("done", 100, "done")
        return {"ok": True}

    manager = JobManager(runner)
    model = tmp_path / "model"
    job = manager.start(
        tmp_path / "in.mp4",
        tmp_path / "out",
        {
            "whisper_engine": "faster-whisper",
            "whisper_model_size": "medium",
            "whisper_device": "cuda",
            "whisper_compute_type": "float16",
            "whisper_vad_filter": True,
            "asr_language": "en",
            "faster_whisper_model": str(model),
        },
    )
    wait_for(job, manager)
    config = seen["transcribe_config"]
    assert isinstance(config, TranscribeConfig)
    assert config.engine == "faster-whisper"
    assert config.model_size == "medium"
    assert config.language == "en"
    assert config.device == "cuda"
    assert config.compute_type == "float16"
    assert config.vad_filter is True
    assert seen["faster_whisper_model"] == str(model)


def test_job_forwards_detailed_zoom_shorts_and_caption_config(tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        seen.update(kwargs)
        progress("done", 100, "done")
        return {"ok": True}

    manager = JobManager(runner)
    job = manager.start(
        tmp_path / "in.mp4",
        tmp_path / "out",
        {
            "zoom_min_scale": 1.1,
            "zoom_max_scale": 1.8,
            "punch_in_scale": 1.3,
            "fade_in_ms": 10,
            "fade_out_ms": 30,
            "fade_curve": "linear",
            "shorts": True,
            "shorts_count": 3,
            "shorts_min_count": 3,
            "shorts_selection_mode": "heuristic",
            "caption_font_family": "Inter",
            "caption_font_size": 96,
            "caption_primary_color": "#F0F0F0",
            "caption_background_color": "#112233",
            "caption_background_opacity": 0.4,
            "caption_position_y": 0.7,
            "caption_word_timing": "proportional",
        },
    )
    wait_for(job, manager)
    assert seen["jl"].fade_in_ms == 10
    assert seen["jl"].fade_out_ms == 30
    assert seen["jl"].fade_curve == "linear"
    assert seen["zooms"].min_scale == 1.1
    assert seen["zooms"].max_scale == 1.8
    config = seen["shorts_config"]
    assert config.min_clips == 3
    assert config.max_clips_to_generate == 3
    assert config.selection_mode == "heuristic"
    assert config.caption_style.font_family == "Inter"
    assert config.caption_style.font_size == 96
    assert config.caption_style.background_color == "#112233"
    assert config.caption_style.background_opacity == 0.4
    assert config.caption_style.position_y == 0.7
    assert config.caption_style.word_timing == "proportional"


def test_idempotency_key_reuses_an_active_job(tmp_path: Path) -> None:
    release = threading.Event()

    def runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        release.wait(timeout=3.0)
        return {"ok": True}

    manager = JobManager(runner)
    source = tmp_path / "source.mp4"
    output = tmp_path / "out"
    first = manager.start(source, output, idempotency_key="run-1", queue=True)
    second = manager.start(source, output, idempotency_key="run-1", queue=True)
    third = manager.start(source, output, idempotency_key="run-2", queue=True)

    assert second.job_id == first.job_id
    assert third.job_id != first.job_id
    release.set()


def test_pause_and_unpause_a_queued_job(tmp_path: Path) -> None:
    release = threading.Event()

    def runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        release.wait(timeout=5.0)
        return {"ok": True}

    manager = JobManager(runner, max_active=1)
    first = manager.start(tmp_path / "a.mp4", tmp_path / "out-a", {})
    second = manager.start(tmp_path / "b.mp4", tmp_path / "out-b", {}, queue=True)
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

    manager = JobManager(runner, max_active=1)
    first = manager.start(tmp_path / "a.mp4", tmp_path / "out-a", {})
    queued = manager.start(tmp_path / "b.mp4", tmp_path / "out-b", {}, queue=True)

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

    manager = JobManager(runner)
    job = manager.start(
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
