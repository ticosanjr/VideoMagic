from pathlib import Path

from fastapi.testclient import TestClient

from videoflow.api.app import create_app


def test_asset_scan_list_tag_and_remove(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "clip.mp4").write_bytes(b"video")
    (assets / "cover.png").write_bytes(b"image")
    client = TestClient(create_app())
    scanned = client.post(
        "/api/v1/assets/scan",
        json={"directory": str(assets), "tags": ["b-roll"]},
    )
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["scanned"] == 2
    listed = client.get("/api/v1/assets", params={"kind": "video"})
    records = listed.json()["assets"]
    assert len(records) == 1
    asset_id = records[0]["id"]
    tagged = client.patch(
        f"/api/v1/assets/{asset_id}",
        json={"tags": ["b-roll", "city"]},
    )
    assert tagged.json()["asset"]["tags"] == ["b-roll", "city"]
    file_response = client.get(f"/api/v1/assets/{asset_id}/file")
    assert file_response.status_code == 200
    assert file_response.content == b"video"
    assert client.delete(f"/api/v1/assets/{asset_id}").status_code == 200
