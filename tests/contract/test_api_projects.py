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


def test_project_crud(client: TestClient, tmp_path: Path) -> None:
    created = client.post(
        "/api/v1/projects",
        json={
            "name": "Interview",
            "source": str(tmp_path / "source.mp4"),
            "output": str(tmp_path / "out"),
        },
    )
    assert created.status_code == 201, created.text
    project = created.json()["project"]
    assert project["name"] == "Interview"

    listed = client.get("/api/v1/projects").json()["projects"]
    assert [item["id"] for item in listed] == [project["id"]]

    updated = client.patch(
        f"/api/v1/projects/{project['id']}",
        json={
            "name": "Interview v2",
            "source": project["source"],
            "output": project["output"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["project"]["name"] == "Interview v2"

    removed = client.delete(f"/api/v1/projects/{project['id']}")
    assert removed.status_code == 200
    assert client.get("/api/v1/projects").json()["projects"] == []


def test_unknown_project_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/projects/missing").status_code == 409
    assert client.delete("/api/v1/projects/missing").status_code == 409
