import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videoflow.api.app import create_app
from videoflow.application.jobs import JobManager


def fake_runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
    progress("probe", 5, "probe")
    output.mkdir(parents=True, exist_ok=True)
    (output / "run.json").write_text("{}", encoding="utf-8")
    return {"ok": True, "video_segment_count": 1}


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
