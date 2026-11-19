from fastapi.testclient import TestClient

from videoflow.api.app import create_app


def test_workflow_routes_and_agents_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    client = TestClient(create_app())
    workspace = tmp_path / "workspace"

    listed = client.get("/api/v1/system/opencode/workflows")
    assert listed.status_code == 200
    ids = {item["workflow_id"] for item in listed.json()["workflows"]}
    assert "youtube-longform" in ids

    created = client.post(
        "/api/v1/system/opencode/workflows",
        json={"workflow_id": "api-flow", "name": "API Flow"},
    )
    assert created.status_code == 201
    assert created.json()["ok"] is True

    fetched = client.get("/api/v1/system/opencode/workflows/api-flow")
    assert fetched.json()["workflow"]["name"] == "API Flow"

    duplicated = client.post(
        "/api/v1/system/opencode/workflows/api-flow/duplicate",
        json={"new_id": "api-flow-copy"},
    )
    assert duplicated.json()["ok"] is True

    synced = client.post(
        "/api/v1/system/opencode/workflows/sync",
        json={"workspace_dir": str(workspace), "overwrite": True},
    )
    assert synced.json()["ok"] is True
    assert (workspace / ".opencode" / "workflows" / "api-flow.md").is_file()

    agents = client.put(
        "/api/v1/system/opencode/agents",
        json={"workspace_dir": str(workspace), "content": "# AGENTS\n"},
    )
    assert agents.json()["ok"] is True
    loaded = client.get("/api/v1/system/opencode/agents", params={"workspace_dir": str(workspace)})
    assert loaded.json()["content"] == "# AGENTS\n"

    restored = client.post(
        "/api/v1/system/opencode/agents/restore",
        json={"workspace_dir": str(workspace), "content": ""},
    )
    assert restored.json()["ok"] is True
    assert "VideoFlow" in restored.json()["content"]


def test_workflow_api_error_branches(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    client = TestClient(create_app())
    workspace = tmp_path / "workspace"

    assert client.get("/api/v1/system/opencode/workflows/missing").json()["ok"] is False
    invalid = client.post(
        "/api/v1/system/opencode/workflows",
        json={"workflow_id": "bad", "markdown_content": "no frontmatter"},
    )
    assert invalid.json()["ok"] is False
    assert (
        client.post(
            "/api/v1/system/opencode/workflows/missing/duplicate",
            json={"new_id": "x"},
        ).json()["ok"]
        is False
    )
    assert client.post("/api/v1/system/opencode/workflows/missing/restore").json()["ok"] is False
    assert (
        client.get(
            "/api/v1/system/opencode/agents", params={"workspace_dir": str(workspace)}
        ).json()["ok"]
        is False
    )
    assert client.delete("/api/v1/system/opencode/workflows/api-flow-copy").json()["ok"] is True
    assert (
        client.put(
            "/api/v1/system/opencode/agents",
            json={"workspace_dir": "/", "content": "x"},
        ).json()["ok"]
        is False
    )
    assert (
        client.post(
            "/api/v1/system/opencode/agents/restore",
            json={"workspace_dir": "/", "content": ""},
        ).json()["ok"]
        is False
    )
