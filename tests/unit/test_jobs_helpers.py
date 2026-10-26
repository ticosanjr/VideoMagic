"""Job helpers: retry scheduling, failure reports, logs, and history."""

from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application import jobs as jobs_module
from videoflow.application.jobs import (
    Job,
    JobManager,
    _duration_ms,
    _provider_value,
    _record_recipe_history,
    _result_dict,
    _write_failure,
    _write_log,
)


def make_job(tmp_path: Path, **options: object) -> Job:
    job = Job(source=tmp_path / "source.mp4", output=tmp_path / "out", options=dict(options))
    job.telemetry.job_id = str(job.job_id)
    return job


def test_provider_value_handles_errors_and_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "videoflow.application.providers.first_provider",
        lambda _capability: (_ for _ in ()).throw(RuntimeError("no providers")),
    )
    assert _provider_value("asr", "base_url") == ""

    monkeypatch.setattr(
        "videoflow.application.providers.first_provider",
        lambda _capability: {"base_url": "http://asr"},
    )
    assert _provider_value("asr", "base_url") == "http://asr"
    assert _provider_value("asr", "missing") == ""

    monkeypatch.setattr(
        "videoflow.application.providers.first_provider", lambda _capability: None
    )
    assert _provider_value("asr", "base_url") == ""


def test_result_dict_forms() -> None:
    assert _result_dict({"a": 1}) == {"a": 1}
    assert _result_dict("text") == {"ok": True, "result": "text"}

    class Result:
        def to_dict(self) -> dict[str, object]:
            return {"ok": True, "value": 2}

    assert _result_dict(Result()) == {"ok": True, "value": 2}

    class Bad:
        def to_dict(self) -> str:
            return "not a dict"

        def __str__(self) -> str:
            return "not a dict"

    assert _result_dict(Bad())["result"] == "not a dict"


def test_duration_ms_edges() -> None:
    assert _duration_ms(None, None) is None
    assert _duration_ms("bad", None) is None
    assert _duration_ms("2020-01-01T00:00:00+00:00", "2020-01-01T00:00:01+00:00") == 1000
    assert _duration_ms("2020-01-01T00:00:00+00:00", None) >= 0


def test_failure_and_log_files(tmp_path: Path) -> None:
    job = make_job(tmp_path, recipe={"id": "podcast"})
    job.output.mkdir(parents=True)
    job.status = "failed"
    job.stage = "render"
    job.message = "boom"
    job.error = {"code": "internal"}

    _write_failure(job)
    _write_log(job)

    failure = job.output / "work" / "failure.json"
    assert failure.is_file()
    assert "boom" in failure.read_text(encoding="utf-8")
    assert (job.output / "job.log").is_file()

    missing = Job(source=tmp_path / "s.mp4", output=tmp_path / "missing", options={})
    _write_log(missing)
    assert not (tmp_path / "missing").exists()


def test_failure_report_survives_disk_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = make_job(tmp_path)
    job.output.mkdir(parents=True)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", fail)

    _write_failure(job)
    _write_log(job)


def test_recipe_history_records_the_recipe_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict[str, object]] = []
    monkeypatch.setattr(
        "videoflow.engine.history.append_run",
        lambda _output, payload: seen.append(dict(payload)),
    )
    job = make_job(tmp_path, recipe={"id": "from-options"})
    job.status = "succeeded"

    _record_recipe_history(job)
    assert seen[-1]["recipe_id"] == "from-options"

    job.result = {"recipe_id": "from-result"}
    _record_recipe_history(job)
    assert seen[-1]["recipe_id"] == "from-result"

    job.options = None  # type: ignore[assignment]
    job.result = None
    _record_recipe_history(job)
    assert seen[-1]["recipe_id"] == ""


def test_retry_scheduling_respects_attempts_and_cancellation() -> None:
    manager = JobManager()
    job = Job(source=Path("/tmp/s.mp4"), output=Path("/tmp/out"), options={})

    assert manager._schedule_retry_locked(job) is False

    job.options = {"max_attempts": 3, "retry_backoff_seconds": 0}
    assert manager._schedule_retry_locked(job) is True
    assert job.attempts == 1
    assert job.status == "queued"

    job.attempts = 2
    assert manager._schedule_retry_locked(job) is False

    job.attempts = 0
    job.cancel_requested = True
    assert manager._schedule_retry_locked(job) is False


def test_retry_thread_is_created_once() -> None:
    manager = JobManager()

    class Alive:
        def is_alive(self) -> bool:
            return True

    manager._retry_thread = Alive()  # type: ignore[assignment]

    manager._ensure_retry_thread()

    assert manager._retry_thread is not None


def test_prune_keeps_only_the_configured_history(tmp_path: Path) -> None:
    manager = JobManager(history=1)
    old = make_job(tmp_path)
    old.status = "succeeded"
    old.finished_at = "2020-01-01T00:00:00+00:00"
    new = make_job(tmp_path)
    new.status = "succeeded"
    new.finished_at = "2021-01-01T00:00:00+00:00"
    manager._jobs[str(old.job_id)] = old
    manager._jobs[str(new.job_id)] = new

    manager._prune()

    assert str(new.job_id) in manager._jobs
    assert str(old.job_id) not in manager._jobs


def test_project_transcript_rejects_invalid_state(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("not json", encoding="utf-8")

    from videoflow.domain.errors import ProjectStateError

    with pytest.raises(ProjectStateError, match="Cannot read project transcript"):
        jobs_module._project_transcript(str(path))
