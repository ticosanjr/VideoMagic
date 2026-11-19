from __future__ import annotations

import time
from pathlib import Path

from tests.contract.api_helpers import _client


def _wait(job):
    for _ in range(300):
        if job.status in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.01)
    return job


def test_run_dag_exposes_nodes_edges_and_retry(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    recipe = {
        "schema_version": 1,
        "id": "demo",
        "name": "Demo",
        "steps": [
            {"id": "ingest", "type": "ingest", "params": {}},
            {"id": "cut", "type": "timeline", "needs": ["ingest"], "params": {}},
        ],
    }
    job = _wait(
        manager.start(
            tmp_path / "source.mp4",
            tmp_path / "out",
            {
                "recipe": recipe,
                "max_attempts": 3,
                "retry_backoff_seconds": 2,
            },
        )
    )
    response = client.get(f"/api/v1/jobs/{job.job_id}/dag")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [node["id"] for node in payload["nodes"]] == ["ingest", "cut"]
    assert payload["edges"] == [{"from": "ingest", "to": "cut"}]
    assert payload["retry"] == {"max_attempts": 3, "backoff_seconds": 2.0}
    assert payload["timing"]["samples"] >= 1
    assert client.get("/api/v1/jobs/missing/dag").status_code == 404
