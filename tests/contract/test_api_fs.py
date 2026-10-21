from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videoflow.api import routes
from videoflow.api.app import create_app
from videoflow.domain.state import MediaInfo


@pytest.fixture
def client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    return TestClient(create_app())


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "media"
    root.mkdir()
    (root / "alpha.mp4").write_bytes(b"video")
    (root / "notes.srt").write_text("1\n", encoding="utf-8")
    (root / ".hidden.mp4").write_bytes(b"hidden")
    (root / "nested").mkdir()
    (root / "nested" / "beta.MOV").write_bytes(b"video")
    return root


def test_roots_are_friendly_and_allowlisted(client: TestClient, tmp_path: Path) -> None:
    response = client.get("/api/v1/fs/roots")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["roots"][0]["path"] == str(tmp_path)
    assert payload["roots"][0]["exists"] is True
    assert payload["roots"][0]["writable"] is True


def test_list_files_filters_extensions_and_hidden_entries(
    client: TestClient, tmp_path: Path
) -> None:
    _tree(tmp_path)
    response = client.get(
        "/api/v1/fs/list",
        params={"path": str(tmp_path), "mode": "file", "extensions": "mp4,mov"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    names = [entry["name"] for entry in payload["entries"]]
    assert names == ["media"]
    assert payload["parent"] is None
    assert payload["breadcrumbs"][0]["path"] == str(tmp_path)
    assert payload["can_write"] is True

    response = client.get(
        "/api/v1/fs/list",
        params={"path": str(tmp_path / "media"), "mode": "file", "extensions": "mp4"},
    )
    names = [entry["name"] for entry in response.json()["entries"]]
    assert names == ["nested", "alpha.mp4"]
    assert ".hidden.mp4" not in names

    response = client.get(
        "/api/v1/fs/list",
        params={
            "path": str(tmp_path / "media"),
            "mode": "file",
            "extensions": "mp4",
            "show_hidden": "true",
        },
    )
    names = [entry["name"] for entry in response.json()["entries"]]
    assert ".hidden.mp4" in names


def test_directory_mode_hides_files_and_query_narrows_results(
    client: TestClient, tmp_path: Path
) -> None:
    root = _tree(tmp_path)
    response = client.get("/api/v1/fs/list", params={"path": str(root), "mode": "directory"})
    assert response.status_code == 200
    assert [entry["name"] for entry in response.json()["entries"]] == ["nested"]

    response = client.get(
        "/api/v1/fs/list",
        params={"path": str(root), "mode": "file", "q": "ALPHA"},
    )
    assert [entry["name"] for entry in response.json()["entries"]] == ["alpha.mp4"]


def test_listing_caps_entries(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "many"
    root.mkdir()
    for index in range(3):
        (root / f"{index}.mp4").write_bytes(b"video")
    response = client.get("/api/v1/fs/list", params={"path": str(root), "mode": "file", "limit": 1})
    assert response.status_code == 200
    assert len(response.json()["entries"]) == 1
    assert response.json()["truncated"] is True


def test_paths_outside_the_allowlist_and_symlink_escapes_are_rejected(
    client: TestClient, tmp_path: Path
) -> None:
    outside = tmp_path.parent / "outside-fs-test"
    outside.mkdir(exist_ok=True)
    try:
        response = client.get("/api/v1/fs/list", params={"path": str(outside)})
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "path_not_allowed"

        root = _tree(tmp_path)
        (root / "escape").symlink_to(outside, target_is_directory=True)
        response = client.get("/api/v1/fs/list", params={"path": str(root), "mode": "directory"})
        assert response.status_code == 200
        assert "escape" not in [entry["name"] for entry in response.json()["entries"]]

        response = client.get("/api/v1/fs/list", params={"path": str(root / "escape")})
        assert response.status_code == 403
    finally:
        outside.rmdir()


def test_missing_path_and_file_as_directory_are_typed_errors(
    client: TestClient, tmp_path: Path
) -> None:
    response = client.get("/api/v1/fs/list", params={"path": str(tmp_path / "missing")})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "path_not_found"

    root = _tree(tmp_path)
    response = client.get("/api/v1/fs/list", params={"path": str(root / "alpha.mp4")})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "not_a_directory"


def test_create_directory_validates_and_returns_the_new_path(
    client: TestClient, tmp_path: Path
) -> None:
    response = client.post(
        "/api/v1/fs/mkdir",
        json={"parent": str(tmp_path), "name": "new-project"},
    )
    assert response.status_code == 201, response.text
    created = response.json()["entry"]
    assert created["kind"] == "directory"
    assert Path(created["path"]).is_dir()
    assert created["path"] == str(tmp_path / "new-project")

    response = client.post(
        "/api/v1/fs/mkdir",
        json={"parent": str(tmp_path), "name": "new-project"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "directory_exists"

    for name in ("../escape", "CON", "bad/name", ""):
        response = client.post("/api/v1/fs/mkdir", json={"parent": str(tmp_path), "name": name})
        assert response.status_code in {409, 422}, name

    response = client.post(
        "/api/v1/fs/mkdir",
        json={"parent": str(tmp_path / "missing"), "name": "inside"},
    )
    assert response.status_code == 404

    outside = tmp_path.parent / "mkdir-outside"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "outside-link"
    link.symlink_to(outside, target_is_directory=True)
    try:
        response = client.post(
            "/api/v1/fs/mkdir",
            json={"parent": str(link), "name": "escape"},
        )
        assert response.status_code == 403
        assert not (outside / "escape").exists()
    finally:
        link.unlink()
        outside.rmdir()


def test_probe_media_returns_metadata_and_rejects_outside_paths(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    root = _tree(tmp_path)
    source = root / "alpha.mp4"
    info = MediaInfo(
        source_path=str(source),
        duration_frames=90,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=48000,
    )
    monkeypatch.setattr(routes, "probe_media", lambda path: info)

    response = client.get("/api/v1/media/probe", params={"path": str(source)})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["name"] == "alpha.mp4"
    assert payload["size_bytes"] == 5
    assert payload["media"]["width"] == 1920

    outside = tmp_path.parent / "outside-probe.mp4"
    outside.write_bytes(b"x")
    try:
        response = client.get("/api/v1/media/probe", params={"path": str(outside)})
        assert response.status_code == 403
    finally:
        outside.unlink()

    response = client.get("/api/v1/media/probe", params={"path": str(tmp_path / "missing.mp4")})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "media_not_found"


def test_modified_at_survives_out_of_range_timestamps() -> None:
    from videoflow.application.filesystem import _modified_at

    assert _modified_at(float("inf")) == "1970-01-01T00:00:00+00:00"
    assert _modified_at(0) == "1970-01-01T00:00:00+00:00"
