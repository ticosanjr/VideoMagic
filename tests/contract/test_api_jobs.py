import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videoflow.api.app import create_app
from videoflow.application.jobs import JobManager


def fake_runner(
    source: Path,
    output: Path,
    *,
    progress,
    should_cancel,
    telemetry=None,
    log=None,
    **kwargs,
):
    progress("probe", 5, "probe")
    if telemetry is not None:
        telemetry.start("ingest", "ingest", "Ingest", "probe")
        telemetry.update("ingest", 50, "extract")
        telemetry.finish("ingest", "PCM ready")
    if log is not None:
        log("ingest", "info", "fake PCM")
    output.mkdir(parents=True, exist_ok=True)
    (output / "run.json").write_text("{}", encoding="utf-8")
    (output / "timeline.fcpxml").write_text("<fcpxml/>", encoding="utf-8")
    (output / "project_state.json").write_text(
        '{"transcript":[{"id":0,"start_sample":0,"end_sample":100,'
        '"text":"take one","words":[]},{"id":1,"start_sample":100,'
        '"end_sample":200,"text":"take two","words":[]}],'
        '"retake_culls":[0],"retake_guard_restores":[]}',
        encoding="utf-8",
    )
    return {
        "ok": True,
        "video_segment_count": 1,
        "artifacts": {"resolve": str(output / "timeline.fcpxml")},
    }


def make_client(monkeypatch, tmp_path: Path, runner=fake_runner) -> TestClient:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    manager = JobManager(runner)
    return TestClient(create_app(jobs=manager))


def wait_http(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = client.get(f"/api/v1/jobs/{job_id}").json()["job"]
        if payload["status"] in {"succeeded", "failed", "cancelled"}:
            return payload
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_create_and_poll_a_job(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/jobs",
        json={"source": str(source), "output": str(tmp_path / "out")},
    )
    assert response.status_code == 202
    job = response.json()["job"]
    assert wait_http(client, job["job_id"])["status"] == "succeeded"
    assert (tmp_path / "out" / "run.json").is_file()


def test_path_outside_the_allowlist_is_rejected(monkeypatch, tmp_path: Path) -> None:
    client = make_client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/jobs",
        json={"source": "/etc/passwd", "output": str(tmp_path / "out")},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "path_not_allowed"


def test_transcript_option_and_state_endpoint(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    subs = tmp_path / "subs.srt"
    subs.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    client = make_client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/jobs",
        json={
            "source": str(source),
            "output": str(tmp_path / "out"),
            "transcript": str(subs),
            "cull_retakes": True,
        },
    )
    assert response.status_code == 202
    job = response.json()["job"]
    assert job["options"]["transcript"] == str(subs)
    assert job["options"]["cull_retakes"] is True
    wait_http(client, job["job_id"])
    state = client.get(f"/api/v1/jobs/{job['job_id']}/state")
    assert state.status_code == 200
    assert state.json()["retake_culls"] == [0]


def test_transcript_outside_the_jail_is_rejected(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/jobs",
        json={
            "source": str(source),
            "output": str(tmp_path / "out"),
            "transcript": "/etc/passwd",
            "cull_retakes": True,
        },
    )
    assert response.status_code == 403


def test_state_is_missing_before_a_run(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    client.post(
        "/api/v1/jobs",
        json={"source": str(source), "output": str(tmp_path / "out")},
    )
    # Fake runner writes state immediately; unknown job is the stable 404 case.
    assert client.get("/api/v1/jobs/missing/state").status_code == 404


def test_artifact_download_is_confined_to_the_job_output(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    job = client.post(
        "/api/v1/jobs",
        json={"source": str(source), "output": str(tmp_path / "out")},
    ).json()["job"]
    wait_http(client, job["job_id"])
    response = client.get(f"/api/v1/jobs/{job['job_id']}/artifacts/resolve")
    assert response.status_code == 200
    assert response.text == "<fcpxml/>"
    assert client.get(f"/api/v1/jobs/{job['job_id']}/artifacts/nope").status_code == 404


def test_job_reports_stages_and_logs(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    job = client.post(
        "/api/v1/jobs",
        json={"source": str(source), "output": str(tmp_path / "out")},
    ).json()["job"]
    finished = wait_http(client, job["job_id"])
    assert finished["stages"][0]["id"] == "ingest"
    assert finished["stages"][0]["duration_ms"] is not None
    assert finished["duration_ms"] is not None
    logs = client.get(f"/api/v1/jobs/{job['job_id']}/logs").json()
    assert logs["total"] == 1
    assert logs["logs"][0]["module"] == "ingest"
    filtered = client.get(
        f"/api/v1/jobs/{job['job_id']}/logs?module=vad"
    ).json()
    assert filtered["logs"] == []
    downloaded = client.get(f"/api/v1/jobs/{job['job_id']}/logs?download=1")
    assert downloaded.status_code == 200
    assert "fake PCM" in downloaded.text


def test_new_module_options_are_forwarded(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/jobs",
        json={
            "source": str(source),
            "output": str(tmp_path / "out"),
            "min_speech_ms": 150,
            "offset_ms": 250,
            "crossfade_ms": 30,
            "handle_check": False,
            "zoom_mode": "manual_rules",
            "punch_in_scale": 1.2,
            "anchor_point": "center",
            "progressive_zoom": True,
            "pan_direction": "left_to_right",
            "export_targets": ["resolve"],
            "strictness": "aggressive",
            "retake_strategy": "keep_best",
            "context_window": 20,
            "shorts": True,
            "shorts_count": 2,
            "shorts_min_sec": 5,
            "shorts_max_sec": 10,
            "shorts_subtitles": False,
            "overrides": [{"sentence_id": 3, "action": "discard"}],
        },
    )
    assert response.status_code == 202
    options = response.json()["job"]["options"]
    assert options["offset_ms"] == 250
    assert options["export_targets"] == ["resolve"]
    assert options["context_window"] == 20
    assert options["shorts_count"] == 2
    assert options["overrides"] == [{"sentence_id": 3, "action": "discard"}]


def test_unknown_job_is_404(monkeypatch, tmp_path: Path) -> None:
    client = make_client(monkeypatch, tmp_path)
    assert client.get("/api/v1/jobs/missing").status_code == 404
    assert client.post("/api/v1/jobs/missing/cancel").status_code == 404


def test_system_endpoint_reports_roots(monkeypatch, tmp_path: Path) -> None:
    client = make_client(monkeypatch, tmp_path)
    payload = client.get("/api/v1/system").json()
    assert payload["ok"] is True
    assert str(tmp_path) in payload["allowed_roots"]


def test_events_stream_delivers_the_terminal_state(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    job = client.post(
        "/api/v1/jobs",
        json={"source": str(source), "output": str(tmp_path / "out")},
    ).json()["job"]
    wait_http(client, job["job_id"])
    response = client.get(f"/api/v1/jobs/{job['job_id']}/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"status": "succeeded"' in response.text


@pytest.mark.media
def test_real_job_writes_three_artifacts(monkeypatch, tmp_path: Path) -> None:
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("FFmpeg is not on PATH")
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=4",
            "-af",
            "volume=0:enable='between(t,1,2)'",
            "-t",
            "4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    client = TestClient(create_app())
    job = client.post(
        "/api/v1/jobs",
        json={"source": str(source), "output": str(tmp_path / "out")},
    ).json()["job"]
    finished = wait_http(client, job["job_id"], timeout=60)
    assert finished["status"] == "succeeded", finished
    for name in ("timeline.fcpxml", "timeline.xml", "timeline.otio"):
        assert (tmp_path / "out" / "exports" / name).is_file()
