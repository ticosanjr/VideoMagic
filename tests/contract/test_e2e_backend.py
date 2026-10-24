"""Backend-real flow: source -> transcript -> timeline -> Short -> review -> export."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videoflow.api.app import create_app

pytestmark = pytest.mark.media


def ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if binary is None:
        pytest.skip("FFmpeg is not on PATH")
    return binary


def media(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6",
            "-af", "volume=0:enable='between(t,1,2)+between(t,3,4)'",
            "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", str(source),
        ],
        check=True,
    )
    srt = tmp_path / "subs.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nPrimeira frase do video.\n\n"
        "2\n00:00:02,000 --> 00:00:03,000\nSegunda frase com resultado.\n\n"
        "3\n00:00:04,000 --> 00:00:06,000\nConclusao final do teste.\n",
        encoding="utf-8",
    )
    return source, srt


def recipe(srt: Path) -> dict:
    return {
        "schema_version": 1,
        "id": "e2e_backend",
        "name": "E2E backend",
        "steps": [
            {"id": "ingest", "type": "ingest", "params": {}},
            {"id": "vad", "type": "audio.vad", "needs": ["ingest"],
             "params": {"engine": "ffmpeg"}},
            {
                "id": "transcribe",
                "type": "transcribe",
                "needs": ["ingest"],
                "params": {"mode": "srt", "srt_path": str(srt)},
            },
            {
                "id": "retakes",
                "type": "retakes.cull",
                "needs": ["vad", "transcribe"],
                "params": {},
            },
            {
                "id": "timeline",
                "type": "edit.timeline",
                "needs": ["vad", "retakes"],
                "params": {},
            },
            {
                "id": "shorts",
                "type": "shorts.select",
                "needs": ["transcribe", "retakes"],
                "params": {
                    "target_duration_min_sec": 1,
                    "target_duration_max_sec": 6,
                    "min_clips": 1,
                    "max_clips_to_generate": 1,
                },
            },
            {
                "id": "captions",
                "type": "shorts.captions",
                "needs": ["shorts"],
                "params": {"enabled": True},
            },
            {
                "id": "render",
                "type": "shorts.render",
                "needs": ["captions"],
                "params": {},
            },
            {
                "id": "export",
                "type": "export.nle",
                "needs": ["timeline"],
                "params": {"targets": ["resolve", "premiere", "kdenlive"]},
            },
            {
                "id": "review",
                "type": "review.queue",
                "needs": ["export", "render"],
                "params": {},
            },
        ],
    }


def test_full_flow_with_a_real_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, srt = media(tmp_path)
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_FFMPEG", ffmpeg())
    client = TestClient(create_app())

    created = client.post(
        "/api/v1/recipes/run",
        json={
            "source": str(source),
            "output": str(tmp_path / "out"),
            "recipe": recipe(srt),
            "resume": False,
        },
    )
    assert created.status_code == 202, created.text
    job_id = created.json()["job"]["job_id"]

    deadline = time.time() + 180
    while time.time() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()["job"]
        if job["status"] in {"succeeded", "failed", "cancelled", "waiting_approval"}:
            break
        time.sleep(0.2)
    assert job["status"] == "succeeded", job.get("error")

    timeline = client.get(f"/api/v1/jobs/{job_id}/timeline")
    assert timeline.status_code == 200, timeline.text
    payload = timeline.json()
    assert payload["video"] and payload["audio"]

    review = client.get(f"/api/v1/jobs/{job_id}/review")
    assert review.status_code == 200, review.text
    approved = client.patch(
        f"/api/v1/jobs/{job_id}/review",
        json={"approved": True, "comment": "e2e", "reviewer": "test"},
    )
    assert approved.status_code == 200, approved.text

    started = time.perf_counter()
    preview = client.post(f"/api/v1/jobs/{job_id}/preview?background=true")
    assert preview.status_code == 200, preview.text
    while time.perf_counter() - started < 30:
        status = client.get(f"/api/v1/jobs/{job_id}/preview/status").json()
        if status["status"] in {"ready", "failed", "cancelled"}:
            break
        time.sleep(0.1)
    assert status["status"] == "ready", status
    assert time.perf_counter() - started < 3.0

    frame = client.get(f"/api/v1/jobs/{job_id}/frame", params={"time": 1.0})
    assert frame.status_code == 200, frame.text
    assert frame.headers["content-type"] == "image/jpeg"
    assert len(frame.content) > 100

    validation = client.post(
        "/api/v1/exports/validate", json={"output": str(tmp_path / "out")}
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["exports"]["fcpxml"]["clips"] >= 1
