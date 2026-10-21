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


def test_capabilities_expose_external_policy() -> None:
    response = TestClient(create_app()).get("/api/v1/capabilities?allow_external=true")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["external_services_allowed"] is True
    ids = {item["id"] for item in payload["capabilities"]}
    assert {"shorts_aspects", "shorts_timeframe", "external_llm"} <= ids


class FakeServer:
    def __init__(self) -> None:
        self.should_exit = False


def test_service_restart_and_shutdown_are_available_to_the_desktop_server() -> None:
    app = create_app()
    server = FakeServer()
    app.state.uvicorn_server = server
    app.state.restart_requested = False
    client = TestClient(app)

    response = client.post("/api/v1/system/restart")
    assert response.status_code == 200
    assert response.json()["action"] == "restart"
    assert server.should_exit is True
    assert app.state.restart_requested is True

    server.should_exit = False
    response = client.post("/api/v1/system/shutdown")
    assert response.status_code == 200
    assert response.json()["action"] == "shutdown"
    assert server.should_exit is True
    assert app.state.restart_requested is False


def test_service_controls_are_rejected_without_a_managed_server() -> None:
    response = TestClient(create_app()).post("/api/v1/system/restart")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "service_control_unavailable"
