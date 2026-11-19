from __future__ import annotations

from fastapi.testclient import TestClient

from videoflow.api import routes_system
from videoflow.api.app import create_app


def test_choose_folder_returns_selected_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(routes_system, "_choose_folder", lambda initial: str(tmp_path / "picked"))
    client = TestClient(create_app())
    response = client.post("/api/v1/system/choose-folder", json={"initial": str(tmp_path)})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "path": str(tmp_path / "picked")}


def test_choose_folder_cancel_and_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    client = TestClient(create_app())
    monkeypatch.setattr(routes_system, "_choose_folder", lambda initial: "")
    assert client.post("/api/v1/system/choose-folder", json={}).json()["cancelled"] is True

    def boom(initial):
        raise RuntimeError("no picker")

    monkeypatch.setattr(routes_system, "_choose_folder", boom)
    response = client.post("/api/v1/system/choose-folder", json={})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "folder_picker_unavailable"
