from fastapi.testclient import TestClient

from videoflow.api.app import create_app, create_http_app


def test_health_is_local_and_answers() -> None:
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "videoflow"
    assert response.json()["version"]


def test_mcp_without_a_trailing_slash_redirects() -> None:
    client = TestClient(create_http_app(), follow_redirects=False)
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert response.status_code == 307
    assert response.headers["location"] == "/mcp/"
