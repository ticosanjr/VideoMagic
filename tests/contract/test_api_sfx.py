from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videoflow.api.app import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    return TestClient(create_app())


def test_sfx_upload_list_and_delete(client: TestClient) -> None:
    created = client.post(
        "/api/v1/assets/sfx",
        params={"name": "whoosh.wav"},
        content=b"RIFFdata",
    )
    assert created.status_code == 201, created.text
    name = created.json()["sfx"]["name"]

    listed = client.get("/api/v1/assets/sfx").json()
    assert [item["name"] for item in listed["sfx"]] == [name]

    removed = client.delete(f"/api/v1/assets/sfx/{name}")
    assert removed.status_code == 200
    assert client.get("/api/v1/assets/sfx").json()["sfx"] == []


def test_sfx_rejects_an_unknown_extension(client: TestClient) -> None:
    response = client.post(
        "/api/v1/assets/sfx",
        params={"name": "notes.txt"},
        content=b"text",
    )
    assert response.status_code == 422


def test_sfx_delete_is_404_for_an_unknown_asset(client: TestClient) -> None:
    assert client.delete("/api/v1/assets/sfx/missing.wav").status_code == 404
