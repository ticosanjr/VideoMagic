from __future__ import annotations

from fastapi.testclient import TestClient

from videoflow.api.app import create_app


def test_openapi_documents_errors_and_preconditions() -> None:
    client = TestClient(create_app())
    schema = client.get("/openapi.json").json()
    assert schema["info"]["x-api-version"]
    assert "ErrorEnvelope" in schema["components"]["schemas"]
    timeline = schema["paths"]["/api/v1/jobs/{job_id}/timeline"]
    assert timeline["get"]["responses"]["200"]["headers"]["ETag"]
    assert timeline["get"]["responses"]["304"]
    names = [item["name"] for item in timeline["patch"]["parameters"]]
    assert "If-Match" in names
    run = schema["paths"]["/api/v1/recipes/run"]["post"]
    assert "202" in run["responses"]
    assert run["responses"]["429"]["description"].startswith("Queue or budget")
