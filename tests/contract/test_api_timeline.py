from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

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
            ),
            VideoSegment(
                clip_id="v2",
                source_in_frame=25,
                source_out_frame=50,
                timeline_in_frame=25,
                timeline_out_frame=50,
            ),
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            ),
            AudioSegment(
                clip_id="v2",
                source_in_sample=48000,
                source_out_sample=96000,
                timeline_in_sample=48000,
                timeline_out_sample=96000,
            ),
        ],
    )
    path = output / "project_state.json"
    path.write_text(state.model_dump_json(), encoding="utf-8")
    return {
        "ok": True,
        "state_path": str(path),
        "artifacts": {},
        "shorts": [],
        "broll_plan": {"Short one": [{"path": "/a.mp4"}, {"path": "/b.mp4"}]},
    }


def _client(monkeypatch, tmp_path: Path) -> tuple[TestClient, JobManager]:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    manager = JobManager(runner=_runner)
    return TestClient(create_app(jobs=manager)), manager


def _job(manager: JobManager, tmp_path: Path):
    job = manager.start(tmp_path / "source.mp4", tmp_path / "out", {})
    for _ in range(300):
        if job.status in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.01)
    assert job.status == "succeeded"
    return job


def test_timeline_split_undo_and_redo(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)

    split = client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline",
        json={"clip_id": "v1", "action": "split", "split_sec": 0.5},
    )
    assert split.status_code == 200, split.text
    assert split.json()["revision"] == 2
    payload = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    assert len(payload["video"]) == 3
    assert payload["can_undo"] is True

    undone = client.post(f"/api/v1/jobs/{job.job_id}/timeline/undo")
    assert undone.status_code == 200, undone.text
    payload = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    assert [clip["id"] for clip in payload["video"]] == ["v1", "v2"]
    assert payload["can_redo"] is True

    redone = client.post(f"/api/v1/jobs/{job.job_id}/timeline/redo")
    assert redone.status_code == 200, redone.text
    assert len(client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()["video"]) == 3


def test_timeline_ripple_delete(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    response = client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline",
        json={"clip_id": "v1", "action": "ripple"},
    )
    assert response.status_code == 200, response.text
    payload = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    assert [clip["id"] for clip in payload["video"]] == ["v2"]
    assert payload["video"][0]["start_sec"] == 0.0


def test_timeline_rejects_split_outside_the_clip(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    response = client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline",
        json={"clip_id": "v2", "action": "split", "split_sec": 0.1},
    )
    assert response.status_code == 422


def test_broll_approval_roundtrip(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    response = client.get(f"/api/v1/jobs/{job.job_id}/broll")
    assert response.status_code == 200
    assert "Short one" in response.json()["plan"]

    saved = client.patch(
        f"/api/v1/jobs/{job.job_id}/broll",
        json={"title": "Short one", "approved": [1], "order": [1, 0]},
    )
    assert saved.status_code == 200, saved.text
    timeline = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    assert timeline["broll_approval"]["Short one"]["approved"] == [1]
    assert timeline["broll_approval"]["Short one"]["order"] == [1, 0]


def test_provider_crud_roundtrip(monkeypatch, tmp_path: Path) -> None:
    client, _ = _client(monkeypatch, tmp_path)
    provider = {
        "id": "local-llm",
        "name": "Local LLM",
        "capability": "llm",
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key_env": "",
        "model": "qwen2.5:7b-instruct",
        "enabled": True,
        "is_default": True,
        "fallback": [],
        "notes": "",
    }
    saved = client.put("/api/v1/providers/local-llm", json=provider)
    assert saved.status_code == 200, saved.text
    listing = client.get("/api/v1/providers").json()
    assert listing["providers"][0]["id"] == "local-llm"
    assert listing["fallbacks"]["llm"][0]["id"] == "local-llm"
    resolved = client.get("/api/v1/providers/resolve", params={"capability": "llm"}).json()
    assert resolved["chain"][0]["id"] == "local-llm"
    removed = client.delete("/api/v1/providers/local-llm")
    assert removed.status_code == 200
    assert client.get("/api/v1/providers").json()["providers"] == []


def test_clip_style_update_roundtrip(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    response = client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline/clip/v1",
        json={
            "transition_type": "fade_to_black",
            "transition_duration_frames": 8,
            "scale": 1.2,
            "fade_in_sec": 0.25,
            "fade_out_sec": 0.5,
        },
    )
    assert response.status_code == 200, response.text
    payload = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    clip = payload["video"][0]
    assert clip["transition"] == "fade_to_black"
    assert clip["transition_frames"] == 8
    assert clip["zoom"] == 1.2
    audio = payload["audio"][0]
    assert audio["fade_in_sec"] == 0.25
    assert audio["fade_out_sec"] == 0.5
    assert payload["revision"] == 2


def test_schedule_crud_and_run_now(monkeypatch, tmp_path: Path) -> None:
    client, _ = _client(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    schedule = {
        "id": "watch-one",
        "kind": "interval",
        "recipe_id": "youtube_talking_head",
        "source": str(source),
        "output": str(tmp_path / "out-scheduled"),
        "interval_seconds": 60,
        "watch_dir": "",
        "pattern": "*.mp4",
        "enabled": True,
        "last_run": "",
        "status": "idle",
        "last_error": "",
        "created_at": "",
        "seen_paths": [],
    }
    saved = client.put("/api/v1/schedules/watch-one", json=schedule)
    assert saved.status_code == 200, saved.text
    listing = client.get("/api/v1/schedules").json()
    assert listing["schedules"][0]["id"] == "watch-one"
    run = client.post("/api/v1/schedules/watch-one/run")
    assert run.status_code == 200, run.text
    assert run.json()["schedule"]["status"] in {"queued", "failed"}
    deleted = client.delete("/api/v1/schedules/watch-one")
    assert deleted.status_code == 200
    assert client.get("/api/v1/schedules").json()["schedules"] == []
