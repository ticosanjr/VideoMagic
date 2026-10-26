"""Recipe version lookup without restoring it."""

from __future__ import annotations

from videoflow.domain.errors import RecipeError
from videoflow.engine.recipes import (
    get_recipe_version,
    recipe_history_dir,
    user_recipes_dir,
)

PAYLOAD = {
    "schema_version": 1,
    "id": "versioned",
    "name": "Versioned",
    "steps": [{"id": "ingest", "type": "ingest", "params": {}}],
}


def write_version(version: str = "123") -> None:
    history = recipe_history_dir("versioned")
    history.mkdir(parents=True, exist_ok=True)
    import json

    (history / f"{version}.json").write_text(json.dumps(PAYLOAD), encoding="utf-8")


def test_reads_a_version_without_restoring_it() -> None:
    write_version()
    recipe = get_recipe_version("versioned", "123")
    assert recipe.name == "Versioned"
    assert not (user_recipes_dir() / "versioned.json").exists()

    try:
        get_recipe_version("versioned", "abc")
    except RecipeError as exc:
        assert "Unknown recipe version" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("invalid version accepted")

    try:
        get_recipe_version("versioned", "999")
    except RecipeError as exc:
        assert "Unknown recipe version" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("missing version accepted")


def test_history_route_returns_the_version(monkeypatch, tmp_path) -> None:
    from tests.contract.test_api_timeline import _client

    client, _manager = _client(monkeypatch, tmp_path)
    write_version("456")

    response = client.get("/api/v1/recipes/versioned/history/456")

    assert response.status_code == 200, response.text
    assert response.json()["recipe"]["name"] == "Versioned"

    missing = client.get("/api/v1/recipes/versioned/history/999")
    assert missing.status_code in {404, 409, 422}
