from __future__ import annotations

import os
from pathlib import Path

from tests.contract.test_api_timeline import _client, _job


def test_missing_job_and_bad_resources_are_actionable(monkeypatch, tmp_path: Path) -> None:
    client, _manager = _client(monkeypatch, tmp_path)
    for path in [
        "/api/v1/jobs/missing/artifacts/x",
        "/api/v1/jobs/missing/thumbnails/x.png",
        "/api/v1/jobs/missing/shorts/0",
        "/api/v1/jobs/missing/shorts/0/file",
        "/api/v1/jobs/missing/shorts/0/thumbnail",
        "/api/v1/jobs/missing/render/status",
        "/api/v1/jobs/missing/render/file",
        "/api/v1/jobs/missing/preview/status",
        "/api/v1/jobs/missing/preview/file",
        "/api/v1/jobs/missing/frame",
        "/api/v1/jobs/missing/frames",
        "/api/v1/jobs/missing/timeline/waveform",
        "/api/v1/jobs/missing/dag",
        "/api/v1/jobs/missing/variants",
        "/api/v1/jobs/missing/assistant/history",
        "/api/v1/jobs/missing/logs",
        "/api/v1/jobs/missing/broll",
        "/api/v1/jobs/missing/review/comments",
    ]:
        response = client.get(path)
        assert response.status_code == 404, path
    assert client.get("/api/v1/assets/missing/file").status_code == 404
    assert client.post(
        "/api/v1/exports/validate", json={"output": str(tmp_path / "none")}
    ).status_code in {200, 404}
    assert client.post("/api/v1/providers/test", json={"base_url": "ftp://bad"}).status_code == 422
    assert (
        client.put(
            "/api/v1/services/definitions/one", json={"id": "two", "name": "Two", "command": "true"}
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/v1/schedules/one",
            json={"id": "two", "recipe_id": "youtube_talking_head"},
        ).status_code
        == 422
    )
    assert client.delete("/api/v1/models/downloads/missing").status_code in {200, 404, 409}


def test_timeline_state_errors_and_track_updates(monkeypatch, tmp_path: Path) -> None:
    from videoflow.domain.state import MediaInfo, ProjectState

    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    state_path = job.output / "project_state.json"
    state = ProjectState.model_validate_json(state_path.read_text())
    state.media_info = None
    state_path.write_text(state.model_dump_json())
    assert client.get(f"/api/v1/jobs/{job.job_id}/timeline/waveform").status_code == 409

    state.media_info = MediaInfo(
        source_path=str(tmp_path / "missing.mp4"),
        duration_frames=10,
        fps_num=30,
        fps_den=1,
        width=10,
        height=10,
        audio_sample_rate=48000,
    )
    state_path.write_text(state.model_dump_json())
    assert client.get(f"/api/v1/jobs/{job.job_id}/timeline/waveform").status_code == 409

    state_path.write_text("{bad", encoding="utf-8")
    assert client.get(f"/api/v1/jobs/{job.job_id}/timeline/waveform").status_code == 422

    fresh, fresh_manager = _client(monkeypatch, tmp_path / "fresh")
    fresh_job = _job(fresh_manager, tmp_path / "fresh")
    assert (
        fresh.put(
            f"/api/v1/jobs/{fresh_job.job_id}/timeline/tracks/bad",
            json={"muted": True},
        ).status_code
        == 409
    )
    assert (
        fresh.put(
            f"/api/v1/jobs/{fresh_job.job_id}/timeline/tracks/video",
            json={"muted": True, "locked": False, "solo": False},
        ).status_code
        == 200
    )
    assert (
        fresh.patch(
            f"/api/v1/jobs/{fresh_job.job_id}/captions/99",
            json={"text": "missing"},
        ).status_code
        < 500
    )
    assert (
        fresh.patch(
            f"/api/v1/jobs/{fresh_job.job_id}/broll",
            json={"title": "Short", "approved": [], "order": []},
        ).status_code
        < 500
    )
    assert fresh.post(f"/api/v1/services/{os.getpid()}/stop").status_code < 500
    assert fresh.post("/api/v1/services/999999/stop").status_code == 404
    assert fresh.post(
        "/api/v1/batches",
        json={
            "source_dir": "/nope",
            "output_root": str(tmp_path),
            "recipe_id": "youtube_talking_head",
        },
    ).status_code in {403, 404, 422}
    assert fresh.get("/api/v1/system/backup").status_code in {200, 404}


def test_provider_secret_name_validation(monkeypatch, tmp_path: Path) -> None:
    client, _manager = _client(monkeypatch, tmp_path)
    payload = {
        "id": "deepseek",
        "name": "DeepSeek",
        "capability": "llm",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key_env": "sk-literal-key",
    }
    rejected = client.put("/api/v1/providers/deepseek", json=payload)
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "invalid_config"
    assert "environment variable name" in rejected.json()["detail"]["message"]

    probed = client.post(
        "/api/v1/providers/test",
        json={
            "base_url": "http://127.0.0.1:9/v1",
            "api_key_env": "sk-literal-key",
            "mode": "models",
        },
    )
    assert probed.status_code == 422
    assert probed.json()["detail"]["code"] == "invalid_config"

    payload["api_key_env"] = " DEEPSEEK_API_KEY "
    saved = client.put("/api/v1/providers/deepseek", json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["provider"]["api_key_env"] == "DEEPSEEK_API_KEY"
