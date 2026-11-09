from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.recipe_jobs import manager_with_runner, start_recipe
from videoflow.api.app import create_app
from videoflow.application.jobs import JobManager
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment


def _runner(source: Path, output: Path, **kwargs):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    state = ProjectState(
        media_info=MediaInfo(
            source_path=str(source),
            duration_frames=100,
            fps_num=25,
            fps_den=1,
            width=320,
            height=240,
            audio_sample_rate=48000,
        ),
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_in_frame=0,
                source_out_frame=25,
                timeline_in_frame=0,
                timeline_out_frame=25,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            )
        ],
    )
    path = output / "project_state.json"
    path.write_text(state.model_dump_json(), encoding="utf-8")
    return {"ok": True, "state_path": str(path), "artifacts": {}, "shorts": []}


def make_client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    return TestClient(create_app(jobs=manager_with_runner(runner=_runner)))


def finished_job(tmp_path: Path, manager: JobManager):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    job = start_recipe(manager, source, tmp_path / "out", {})
    for _ in range(300):
        if job.status in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.01)
    assert job.status == "succeeded", job.error
    return job


def test_waveform_endpoint_returns_peaks(monkeypatch, tmp_path: Path) -> None:
    client = make_client(monkeypatch, tmp_path)
    job = finished_job(tmp_path, client.app.state.jobs)

    calls: list[dict[str, object]] = []

    import videoflow.api.routes_timeline as routes

    def fake_peaks(source, *, start_sec, end_sec, buckets):
        calls.append(
            {
                "source": str(source),
                "start_sec": start_sec,
                "end_sec": end_sec,
                "buckets": buckets,
            }
        )
        return {"ok": True, "peaks": [0.1, 0.5, 1.0], "bucket_sec": 0.05}

    monkeypatch.setattr(routes, "peaks_for_range", fake_peaks)
    response = client.get(
        f"/api/v1/jobs/{job.job_id}/timeline/waveform",
        params={"start": 0.5, "end": 1.5, "buckets": 120},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["peaks"] == [0.1, 0.5, 1.0]
    assert calls[0]["start_sec"] == pytest.approx(0.5)
    assert calls[0]["buckets"] == 120


def test_timeline_exposes_audio_source_ranges(monkeypatch, tmp_path: Path) -> None:
    client = make_client(monkeypatch, tmp_path)
    job = finished_job(tmp_path, client.app.state.jobs)

    payload = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()

    assert payload["audio"][0]["source_in_sec"] == 0.0
    assert payload["audio"][0]["source_out_sec"] == pytest.approx(1.0)
    assert payload["media"]["audio_sample_rate"] == 48000


def test_waveform_requires_a_state_file(monkeypatch, tmp_path: Path) -> None:
    client = make_client(monkeypatch, tmp_path)
    assert client.get("/api/v1/jobs/missing/timeline/waveform").status_code == 404
