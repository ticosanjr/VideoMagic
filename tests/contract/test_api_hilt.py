from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from videoflow.api.app import create_app
from videoflow.application.jobs import JobManager


def _client(monkeypatch, tmp_path: Path) -> tuple[TestClient, JobManager]:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    manager = JobManager()
    return TestClient(create_app(jobs=manager)), manager


def _wait(manager: JobManager, job_id: str, statuses: set[str]) -> object:
    deadline = time.time() + 10
    while time.time() < deadline:
        job = manager.get(job_id)
        if job.status in statuses:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not reach {statuses}: {manager.get(job_id).status}")


def _base_recipe(steps: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "id": "hilt_api",
        "name": "HILT API",
        "steps": steps,
    }


def test_human_input_pauses_and_resumes(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    recipe = _base_recipe(
        [
            {
                "id": "ask",
                "type": "human.input",
                "params": {
                    "gate_id": "brief",
                    "title": "Brief",
                    "questions": [
                        {"id": "topic", "label": "Topic", "type": "text", "required": True}
                    ],
                },
            },
            {
                "id": "index",
                "type": "assets.index",
                "needs": ["ask"],
                "params": {"asset_dir": ""},
            },
        ]
    )
    job = manager.start(
        source, tmp_path / "out", {"mode": "recipe", "recipe": recipe}, queue=True
    )
    waiting = _wait(manager, str(job.job_id), {"waiting_input", "failed"})
    assert waiting.status == "waiting_input", waiting.error
    interaction = waiting.error["interaction"]
    assert interaction["questions"][0]["id"] == "topic"

    listed = client.get(f"/api/v1/jobs/{job.job_id}/interactions")
    assert listed.status_code == 200
    assert listed.json()["interactions"][0]["status"] == "pending"

    response = client.post(
        f"/api/v1/jobs/{job.job_id}/interactions/{interaction['interaction_id']}/respond",
        json={"action": "submit", "answers": {"topic": "Corruption"}, "comment": "ok"},
    )
    assert response.status_code == 202, response.text
    resumed_id = response.json()["resumed_job_id"]
    done = _wait(manager, resumed_id, {"succeeded", "failed"})
    assert done.status == "succeeded", done.error
    assert manager.get(str(job.job_id)).status == "answered"

    answers = Path(done.output) / "hilt" / interaction["interaction_id"] / "answers.json"
    assert answers.is_file()
    assert "Corruption" in answers.read_text(encoding="utf-8")


def test_human_files_upload_and_resume(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    recipe = _base_recipe(
        [
            {
                "id": "files",
                "type": "human.files",
                "params": {
                    "gate_id": "research",
                    "title": "Research",
                    "files": [
                        {
                            "id": "agent_a",
                            "label": "Agent A",
                            "required": True,
                            "accept": [".md"],
                            "target": "research/agent-a.md",
                        }
                    ],
                },
            },
            {
                "id": "index",
                "type": "assets.index",
                "needs": ["files"],
                "params": {"asset_dir": ""},
            },
        ]
    )
    job = manager.start(
        source, tmp_path / "out", {"mode": "recipe", "recipe": recipe}, queue=True
    )
    waiting = _wait(manager, str(job.job_id), {"waiting_input", "failed"})
    assert waiting.status == "waiting_input", waiting.error
    interaction_id = waiting.error["interaction"]["interaction_id"]

    upload = client.post(
        f"/api/v1/jobs/{job.job_id}/interactions/{interaction_id}/files",
        data={"request_id": "agent_a"},
        files={"files": ("agent-a.md", b"# Agent A\n", "text/markdown")},
    )
    assert upload.status_code == 201, upload.text

    response = client.post(
        f"/api/v1/jobs/{job.job_id}/interactions/{interaction_id}/respond",
        json={"action": "submit"},
    )
    assert response.status_code == 202, response.text
    resumed_id = response.json()["resumed_job_id"]
    done = _wait(manager, resumed_id, {"succeeded", "failed"})
    assert done.status == "succeeded", done.error
    assert (tmp_path / "out" / "research" / "agent-a.md").read_text(
        encoding="utf-8"
    ) == "# Agent A\n"


def test_pending_endpoint_lists_the_waiting_job(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    recipe = _base_recipe(
        [
            {
                "id": "ask",
                "type": "human.input",
                "params": {
                    "gate_id": "brief",
                    "title": "Brief",
                    "questions": [{"id": "topic", "label": "Topic", "type": "text"}],
                },
            }
        ]
    )
    job = manager.start(
        source, tmp_path / "out", {"mode": "recipe", "recipe": recipe}, queue=True
    )
    _wait(manager, str(job.job_id), {"waiting_input", "failed"})
    pending = client.get("/api/v1/hilt/pending")
    assert pending.status_code == 200
    items = pending.json()["interactions"]
    assert any(item["job_id"] == str(job.job_id) for item in items)


def test_hilt_channel_and_secret_routes(monkeypatch, tmp_path: Path) -> None:
    client, _manager = _client(monkeypatch, tmp_path)
    channels = client.get("/api/v1/hilt/channels")
    assert channels.status_code == 200
    ids = {item["id"] for item in channels.json()["channels"]}
    assert {"local", "email", "slack", "signal"} <= ids

    local = client.post("/api/v1/hilt/test", json={"channel": "local"})
    assert local.status_code == 200
    assert local.json()["ok"] is True

    listing = client.get("/api/v1/hilt/secrets")
    assert listing.status_code == 200
    assert "VIDEOWFLOW_SMTP_PASSWORD" in listing.json()["secrets"]

    rejected = client.post(
        "/api/v1/hilt/secrets",
        json={"name": "NOT_ALLOWED", "value": "x"},
    )
    assert rejected.status_code == 409

    saved = client.post(
        "/api/v1/hilt/secrets",
        json={"name": "VIDEOWFLOW_SMTP_PASSWORD", "value": "secret"},
    )
    assert saved.status_code == 200
    assert client.get("/api/v1/hilt/secrets").json()["secrets"][
        "VIDEOWFLOW_SMTP_PASSWORD"
    ] is True


def test_slack_url_verification(monkeypatch, tmp_path: Path) -> None:
    client, _manager = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/hilt/slack/events",
        json={"type": "url_verification", "challenge": "abc"},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "challenge": "abc"}


def test_hilt_artifact_download_and_cancel(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    output = tmp_path / "out"
    output.mkdir()
    (output / "manual.txt").write_text("review me", encoding="utf-8")
    recipe = _base_recipe(
        [
            {
                "id": "gate",
                "type": "human.gate",
                "params": {
                    "gate_id": "review",
                    "title": "Review",
                    "artifacts": ["manual.txt"],
                },
            }
        ]
    )
    job = manager.start(
        source, output, {"mode": "recipe", "recipe": recipe}, queue=True
    )
    waiting = _wait(manager, str(job.job_id), {"waiting_approval", "failed"})
    assert waiting.status == "waiting_approval", waiting.error
    interaction = waiting.error["interaction"]
    interaction_id = interaction["interaction_id"]
    artifact_id = interaction["artifacts"][0]["id"]
    download = client.get(
        f"/api/v1/jobs/{job.job_id}/interactions/{interaction_id}/artifacts/{artifact_id}"
    )
    assert download.status_code == 200
    assert download.content == b"review me"

    cancelled = client.post(
        f"/api/v1/jobs/{job.job_id}/interactions/{interaction_id}/cancel"
    )
    assert cancelled.status_code == 200
    assert manager.get(str(job.job_id)).status == "cancelled"


def test_interaction_list_get_and_missing_artifact(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    recipe = _base_recipe(
        [
            {
                "id": "gate",
                "type": "human.gate",
                "params": {
                    "gate_id": "review",
                    "title": "Review",
                    "artifacts": ["manual.txt"],
                },
            }
        ]
    )
    output = tmp_path / "out"
    output.mkdir()
    (output / "manual.txt").write_text("review", encoding="utf-8")
    job = manager.start(
        source, output, {"mode": "recipe", "recipe": recipe}, queue=True
    )
    waiting = _wait(manager, str(job.job_id), {"waiting_approval", "failed"})
    assert waiting.status == "waiting_approval", waiting.error
    (output / "manual.txt").unlink()
    listed = client.get(f"/api/v1/jobs/{job.job_id}/interactions")
    assert listed.status_code == 200
    interaction = listed.json()["interactions"][0]
    detail = client.get(
        f"/api/v1/jobs/{job.job_id}/interactions/{interaction['interaction_id']}"
    )
    assert detail.status_code == 200
    artifact_id = interaction["artifacts"][0]["id"]
    missing = client.get(
        f"/api/v1/jobs/{job.job_id}/interactions/{interaction['interaction_id']}"
        f"/artifacts/{artifact_id}"
    )
    assert missing.status_code == 404


def test_upload_with_unknown_file_request_is_rejected(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    recipe = _base_recipe(
        [
            {
                "id": "files",
                "type": "human.files",
                "params": {
                    "gate_id": "files",
                    "title": "Files",
                    "files": [{"id": "a", "label": "A", "required": True, "accept": [".md"]}],
                },
            }
        ]
    )
    job = manager.start(
        source, tmp_path / "out", {"mode": "recipe", "recipe": recipe}, queue=True
    )
    waiting = _wait(manager, str(job.job_id), {"waiting_input", "failed"})
    assert waiting.status == "waiting_input", waiting.error
    interaction_id = waiting.error["interaction"]["interaction_id"]
    response = client.post(
        f"/api/v1/jobs/{job.job_id}/interactions/{interaction_id}/files",
        data={"request_id": "unknown"},
        files={"files": ("a.md", b"x", "text/markdown")},
    )
    assert response.status_code == 409


def test_hilt_invalid_payloads_and_waiting_guard(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    for path in ("/api/v1/hilt/slack/events", "/api/v1/hilt/email/inbound"):
        broken = client.post(
            path,
            content=b"{not json",
            headers={"content-type": "application/json"},
        )
        assert broken.status_code == 409

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    job = manager.start(
        source,
        tmp_path / "out",
        {"mode": "recipe", "recipe": _base_recipe([])},
        queue=True,
    )
    _wait(manager, str(job.job_id), {"succeeded", "failed"})
    guarded = client.post(
        f"/api/v1/jobs/{job.job_id}/interactions/missing/respond",
        json={"action": "submit"},
    )
    assert guarded.status_code == 409
