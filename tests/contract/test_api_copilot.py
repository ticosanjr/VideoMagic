from __future__ import annotations

from pathlib import Path

from videoflow.application import llm_factory


class FakeClient:
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, prompt: str, schema_name: str):
        return self.payload


def test_copilot_recipe_route(monkeypatch, tmp_path: Path) -> None:
    from tests.contract.test_api_timeline import _client

    client, _manager = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        llm_factory,
        "build_llm",
        lambda: FakeClient(
            {
                "schema_version": 1,
                "id": "copilot_demo",
                "name": "Demo",
                "steps": [{"id": "ingest", "type": "ingest", "params": {}}],
            }
        ),
    )
    response = client.post("/api/v1/copilot/recipe", json={"prompt": "ingest"})
    assert response.status_code == 200, response.text
    assert response.json()["recipe"]["id"] == "copilot_demo"


def test_copilot_timeline_route_applies_edits(monkeypatch, tmp_path: Path) -> None:
    from tests.contract.test_api_timeline import _client, _job

    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    monkeypatch.setattr(
        llm_factory,
        "build_llm",
        lambda: FakeClient(
            {
                "edits": [
                    {"clip_id": "v1", "action": "trim", "start_sec": 0.0, "end_sec": 0.5}
                ],
                "reasoning": "shorten",
            }
        ),
    )
    response = client.post(
        f"/api/v1/jobs/{job.job_id}/copilot/timeline",
        json={"prompt": "shorten the first clip", "apply": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["applied"] is True
    assert response.json()["revision"] >= 2
