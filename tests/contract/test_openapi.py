from __future__ import annotations

from fastapi.testclient import TestClient

from videoflow.api.app import create_app


def test_openapi_documents_the_mcp_control_plane() -> None:
    client = TestClient(create_app())
    schema = client.get("/openapi.json").json()
    assert schema["info"]["x-api-version"]
    assert "ErrorEnvelope" in schema["components"]["schemas"]
    assert "/health" in schema["paths"]
    assert "/api/v1/jobs" in schema["paths"]
    assert "/api/v1/jobs/{job_id}" in schema["paths"]
    assert "/api/v1/capabilities" in schema["paths"]
    assert "/api/v1/system/doctor" in schema["paths"]
    assert "/api/v1/gpu/status" in schema["paths"]
    assert "/api/v1/recipes/run" not in schema["paths"]
    assert "/api/v1/jobs/{job_id}/timeline" not in schema["paths"]
