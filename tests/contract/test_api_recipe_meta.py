from __future__ import annotations

from tests.contract.test_api_timeline import _client


def test_recipe_favorite_recent_and_metadata(monkeypatch, tmp_path) -> None:
    client, _manager = _client(monkeypatch, tmp_path)
    listed = client.get("/api/v1/recipes").json()["recipes"]
    by_id = {item["id"]: item for item in listed}
    assert by_id["recut_replacement"]["favorite"] is True
    assert by_id["recut_replacement"]["use_count"] == 0

    favorited = client.post(
        "/api/v1/recipes/youtube_talking_head/favorite", json={"favorite": True}
    )
    assert favorited.status_code == 200
    assert favorited.json()["meta"]["favorite"] is True

    touched = client.post("/api/v1/recipes/youtube_talking_head/touch")
    assert touched.status_code == 200
    assert touched.json()["meta"]["use_count"] == 1

    tagged = client.patch(
        "/api/v1/recipes/youtube_talking_head/meta",
        json={"tags": ["interview", "long"]},
    )
    assert tagged.status_code == 200
    refreshed = {
        item["id"]: item for item in client.get("/api/v1/recipes").json()["recipes"]
    }
    assert refreshed["youtube_talking_head"]["favorite"] is True
    assert refreshed["youtube_talking_head"]["tags"] == ["interview", "long"]
    assert refreshed["youtube_talking_head"]["last_used_at"]

    missing = client.post("/api/v1/recipes/missing/favorite", json={"favorite": True})
    assert missing.status_code in {404, 422}


def test_recipe_preflight_reports_checks(monkeypatch, tmp_path) -> None:
    client, _manager = _client(monkeypatch, tmp_path)
    recipe = {
        "schema_version": 1,
        "id": "preflight_contract",
        "name": "Preflight",
        "steps": [
            {
                "id": "voice",
                "type": "narration.synthesize",
                "needs": [],
                "params": {},
            }
        ],
    }
    response = client.post(
        "/api/v1/recipes/preflight",
        json={
            "recipe": recipe,
            "output": str(tmp_path / "out"),
            "variables": {},
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert isinstance(payload["checks"], list)
    assert payload["ready"] in {True, False}

    missing = client.post(
        "/api/v1/recipes/preflight",
        json={"recipe": recipe, "output": str(tmp_path / "out")},
    )
    assert missing.status_code == 200
    assert any(item["id"] == "input.output" for item in missing.json()["checks"])
