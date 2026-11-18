"""Style catalog REST routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from videoflow.api.app import create_app


def test_style_routes_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    client = TestClient(create_app())
    workspace = tmp_path / "workspace"

    response = client.get("/api/v1/styles")
    assert response.status_code == 200
    assert any(item["style_id"] == "canal-paula-reels" for item in response.json()["styles"])

    created = client.post(
        "/api/v1/styles",
        json={
            "style_id": "api-style",
            "name": "API Style",
            "target_lufs": -14.5,
            "palette": ["#000000"],
            "export_targets": ["mp4_youtube", "resolve"],
            "workspace_dir": str(workspace),
        },
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["ok"] is True
    assert payload["style"]["target_lufs"] == -14.5
    assert (workspace / "presets" / "api-style.md").is_file()

    fetched = client.get("/api/v1/styles/api-style")
    assert fetched.json()["style"]["name"] == "API Style"

    learned = client.post(
        "/api/v1/styles/api-style/learn",
        json={"notes": ["Cortar antes de 1s"], "max_rules": 15},
    )
    assert learned.json()["count"] == 1

    synced = client.post(
        "/api/v1/styles/sync",
        json={"workspace_dir": str(workspace), "overwrite": True},
    )
    assert synced.json()["ok"] is True

    deleted = client.delete("/api/v1/styles/api-style")
    assert deleted.json()["deleted"] is True


def test_style_routes_report_missing_style(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    client = TestClient(create_app())

    response = client.get("/api/v1/styles/missing")

    assert response.json()["ok"] is False
    assert response.json()["code"] == "style_not_found"


def test_style_routes_errors(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    client = TestClient(create_app())

    invalid = client.post("/api/v1/styles", json={"name": "No id"})
    assert invalid.json()["code"] == "invalid_style"

    missing = client.post("/api/v1/styles/missing/learn", json={"notes": ["x"]})
    assert missing.json()["code"] == "style_not_found"

    assert client.delete("/api/v1/styles/missing").json()["deleted"] is False


def test_style_duplicate_restore_and_errors(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    client = TestClient(create_app())

    duplicated = client.post(
        "/api/v1/styles/canal-paula-reels/duplicate",
        json={"new_id": "canal-paula-copy", "name": "Cópia"},
    )
    assert duplicated.status_code == 200
    assert duplicated.json()["ok"] is True
    assert (tmp_path / "home" / "styles" / "canal-paula-copy.md").is_file()

    restored = client.post("/api/v1/styles/canal-paula-reels/restore")
    assert restored.json()["ok"] is True

    assert (
        client.post("/api/v1/styles/missing/duplicate", json={"new_id": "x"}).json()["ok"] is False
    )
    assert client.post("/api/v1/styles/missing/restore").json()["ok"] is False
