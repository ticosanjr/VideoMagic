"""Regression: library deletes and config imports use the right error contract."""

from __future__ import annotations

import pytest

from tests.contract.test_api_timeline import _client


@pytest.mark.parametrize("kind", ["music", "images", "fonts"])
def test_missing_library_assets_return_404(monkeypatch, tmp_path, kind: str) -> None:
    client, _manager = _client(monkeypatch, tmp_path)

    response = client.delete(f"/api/v1/assets/{kind}/missing.mp3")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "asset_not_found"


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 2, "options": {}},
    ],
)
def test_invalid_config_imports_return_422(monkeypatch, tmp_path, payload: dict) -> None:
    client, _manager = _client(monkeypatch, tmp_path)

    response = client.post("/api/v1/config/import", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_config"


def test_config_import_round_trip(monkeypatch, tmp_path) -> None:
    client, _manager = _client(monkeypatch, tmp_path)
    exported = client.post("/api/v1/config/export", json={"options": {}})

    response = client.post(
        "/api/v1/config/import",
        json={"schema_version": 1, "options": exported.json()["envelope"]["options"]},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
