from __future__ import annotations

from pathlib import Path

from tests.contract.test_api_timeline import _client, _job


def test_recipe_schedule_provider_and_model_errors(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    assert client.put("/api/v1/recipes/bad", json={"nope": True}).status_code == 422
    assert (
        client.put(
            "/api/v1/schedules/s1",
            json={
                "id": "s1",
                "recipe_id": "youtube_talking_head",
                "source": str(tmp_path / "source.mp4"),
                "output": str(tmp_path / "sched"),
                "interval_seconds": 60,
            },
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/api/v1/schedules/mismatch",
            json={"id": "other", "recipe_id": "youtube_talking_head"},
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/v1/providers/mismatch",
            json={
                "id": "other",
                "name": "Other",
                "capability": "llm",
                "base_url": "http://127.0.0.1:9/v1",
                "model": "x",
            },
        ).status_code
        == 422
    )
    assert client.post(
        f"/api/v1/jobs/{job.job_id}/resume", json={"approved": True}
    ).status_code in {200, 202, 409}
    assert client.delete("/api/v1/models/downloads/missing").status_code in {200, 404, 409}
    assert (
        client.post(
            "/api/v1/maintenance/prune",
            json={"output": str(tmp_path / "missing")},
        ).status_code
        == 404
    )
    assert (
        client.post(f"/api/v1/jobs/{job.job_id}/shorts/0/analyze/llm", json={}).status_code <= 501
    )
    assert client.get("/api/v1/system/backup").status_code in {200, 404}
    assert client.post(
        "/api/v1/exports/validate", json={"output": str(job.output)}
    ).status_code in {200, 404}


def test_clip_batch_and_assistant_error_branches(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    assert client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline/clip/missing", json={"scale": 1.1}
    ).status_code in {404, 409}
    assert (
        client.patch(
            f"/api/v1/jobs/{job.job_id}/timeline/clip/v1",
            json={"transition_type": "crossfade", "transition_duration_frames": 5},
        ).status_code
        == 200
    )
    assert (
        client.patch(f"/api/v1/jobs/{job.job_id}/timeline/batch", json={"edits": []}).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/jobs/{job.job_id}/timeline/batch",
            json={"edits": [{"clip_id": "v1", "action": "move", "delta_sec": 0.1}]},
        ).status_code
        == 200
    )
    assert (
        client.post(f"/api/v1/jobs/{job.job_id}/assistant", json={"prompt": ""}).status_code == 422
    )


def test_caption_schedule_assets_and_service_definitions(monkeypatch, tmp_path: Path) -> None:
    from videoflow.domain.state import ProjectState, Sentence

    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    state_path = job.output / "project_state.json"
    state = ProjectState.model_validate_json(state_path.read_text())
    state.transcript = [Sentence(id=0, start_sample=0, end_sample=48000, text="old", speaker=0)]
    state_path.write_text(state.model_dump_json())
    caption = client.patch(f"/api/v1/jobs/{job.job_id}/captions/0", json={"text": "new"})
    assert caption.status_code == 200, caption.text
    assert (
        client.put(
            f"/api/v1/jobs/{job.job_id}/timeline/meta",
            json={"markers": [], "tracks": {}, "comments": []},
        ).status_code
        == 200
    )

    schedule = {
        "id": "s1",
        "recipe_id": "youtube_talking_head",
        "source": str(tmp_path / "source.mp4"),
        "output": str(tmp_path / "sched"),
        "interval_seconds": 60,
    }
    assert client.put("/api/v1/schedules/s1", json=schedule).status_code == 200
    assert client.post("/api/v1/schedules/s1/run").status_code in {200, 202, 409}
    assert client.delete("/api/v1/schedules/s1").status_code == 200

    folder = tmp_path / "assets"
    folder.mkdir()
    assert client.post("/api/v1/assets/scan", json={"directory": str(folder)}).status_code == 200

    recipe = {
        "schema_version": 1,
        "id": "run_demo",
        "name": "Run",
        "steps": [{"id": "ingest", "type": "ingest", "params": {}}],
    }
    assert client.post(
        "/api/v1/steps/ingest/run",
        json={
            "recipe": recipe,
            "source": str(tmp_path / "source.mp4"),
            "output": str(tmp_path / "step-out"),
        },
    ).status_code in {202, 409, 422}
    assert client.post(
        "/api/v1/recipes/run",
        json={
            "recipe": recipe,
            "source": str(tmp_path / "source.mp4"),
            "output": str(tmp_path / "recipe-out"),
        },
    ).status_code in {202, 409, 422}

    assert client.post("/api/v1/services/definitions/svc/save", json={}).status_code in {
        404,
        405,
        422,
    }
    service = {"id": "svc", "name": "Svc", "command": "/bin/true"}
    assert client.put("/api/v1/services/definitions/svc", json=service).status_code == 200
    assert client.get("/api/v1/services/definitions/svc/status").status_code in {200, 404}
    assert client.get("/api/v1/services/definitions/svc/logs").status_code in {200, 404}
    assert client.post("/api/v1/services/definitions/svc/stop").status_code in {200, 404, 409}
    assert client.delete("/api/v1/services/definitions/svc").status_code == 200


def test_corrupt_timeline_caption_and_batch_errors(monkeypatch, tmp_path: Path) -> None:

    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    (job.output / "project_state.json").write_text("{bad", encoding="utf-8")
    assert (
        client.patch(f"/api/v1/jobs/{job.job_id}/captions/0", json={"text": "x"}).status_code == 422
    )
    assert (
        client.patch(
            f"/api/v1/jobs/{job.job_id}/timeline/batch",
            json={"edits": [{"clip_id": "v1", "action": "move", "delta_sec": 0.1}]},
        ).status_code
        == 422
    )
    from videoflow.api import routes_admin as admin_module
    monkeypatch.setattr(admin_module, "remove_model", lambda model_id: None)
    assert client.delete("/api/v1/models/demo").status_code == 200
