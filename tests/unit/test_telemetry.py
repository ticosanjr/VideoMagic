from videoflow.application.telemetry import JobTelemetry


def test_stage_lifecycle_has_timestamps_and_duration() -> None:
    telemetry = JobTelemetry()
    telemetry.start("vad", "vad", "Voice detect", "starting")
    telemetry.update("vad", 45, "half")
    telemetry.finish("vad", "done")
    stage = telemetry.stages()[0]
    assert stage["status"] == "succeeded"
    assert stage["progress"] == 100
    assert stage["message"] == "done"
    assert stage["started_at"]
    assert stage["finished_at"]
    assert stage["duration_ms"] is not None


def test_stage_failure_and_running_failure() -> None:
    telemetry = JobTelemetry()
    telemetry.start("ingest", "ingest", "Ingest", "starting")
    telemetry.fail_running("boom")
    stage = telemetry.stages()[0]
    assert stage["status"] == "failed"
    assert stage["error"] == "boom"


def test_stage_cancellation() -> None:
    telemetry = JobTelemetry()
    telemetry.start("vad", "vad", "Voice detect", "starting")
    telemetry.cancel("vad")
    assert telemetry.stages()[0]["status"] == "cancelled"


def test_logs_are_bounded_and_filterable() -> None:
    telemetry = JobTelemetry(max_logs=3)
    telemetry.log("ingest", "info", "one")
    telemetry.log("vad", "info", "two")
    telemetry.log("vad", "error", "three")
    telemetry.log("export", "info", "four")
    assert telemetry.log_count() == 3
    assert [row["message"] for row in telemetry.logs(module="vad")] == ["two", "three"]
    assert [row["message"] for row in telemetry.logs(level="error")] == ["three"]
    assert telemetry.dump().count("\n") == 3


def test_empty_log_does_not_add_a_line() -> None:
    telemetry = JobTelemetry()
    telemetry.log("ingest", "info", "")
    assert telemetry.log_count() == 0
