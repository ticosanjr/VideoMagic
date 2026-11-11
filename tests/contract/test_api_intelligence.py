from __future__ import annotations

from fastapi.testclient import TestClient

from videoflow.api.app import create_app


def test_intelligence_status_and_tasks() -> None:
    client = TestClient(create_app())
    status = client.get("/api/v1/intelligence/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["ok"] is True
    assert "providers" in payload
    assert "telemetry" in payload

    tasks = client.get("/api/v1/intelligence/tasks")
    assert tasks.status_code == 200
    assert "default_order" in tasks.json()


def test_intelligence_models_rejects_unknown_provider() -> None:
    client = TestClient(create_app())
    response = client.get(
        "/api/v1/intelligence/models", params={"provider": "missing"}
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "provider_not_found"
