"""Built-in and user recipe catalog, path resolution, and history."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.core.recipe import parse_recipe, recipe_to_dict
from videoflow.domain.errors import RecipeError
from videoflow.engine import recipes
from videoflow.engine.recipes import (
    builtin_recipe,
    get_recipe,
    list_recipe_history,
    list_recipes,
    resolve_recipe_paths,
    restore_recipe_version,
    save_user_recipe,
    user_recipes_dir,
)


def payload(recipe_id: str = "mine", **overrides: object) -> dict:
    body = {
        "schema_version": 1,
        "id": recipe_id,
        "name": "Mine",
        "description": "Custom",
        "steps": [{"id": "ingest", "type": "ingest", "params": {}}],
    }
    body.update(overrides)
    return body


def test_builtin_recipe_lookup() -> None:
    builtin = builtin_recipe("best_moments")
    assert builtin.name

    with pytest.raises(RecipeError, match="Unknown recipe"):
        builtin_recipe("missing")


def test_get_recipe_reads_user_files_and_validates_ids(tmp_path: Path) -> None:
    user_recipes_dir().mkdir(parents=True, exist_ok=True)
    (user_recipes_dir() / "mine.json").write_text(json.dumps(payload()), encoding="utf-8")

    assert get_recipe("mine").name == "Mine"
    assert get_recipe("best_moments").id == "best_moments"
    with pytest.raises(RecipeError, match="Invalid recipe id"):
        get_recipe("../escape")
    with pytest.raises(RecipeError, match="Unknown recipe"):
        get_recipe("missing")


def test_list_recipes_skips_invalid_and_duplicates(tmp_path: Path) -> None:
    user_recipes_dir().mkdir(parents=True, exist_ok=True)
    (user_recipes_dir() / "a.json").write_text(json.dumps(payload()), encoding="utf-8")
    (user_recipes_dir() / "b.json").write_text(json.dumps(payload()), encoding="utf-8")
    (user_recipes_dir() / "bad.json").write_text("not json", encoding="utf-8")

    listed = {item["id"]: item for item in list_recipes()}

    assert listed["mine"]["source"].endswith("a.json")
    assert listed["best_moments"]["source"] == "builtin"
    assert "bad" not in listed


def test_resolve_recipe_paths_covers_media_params(tmp_path: Path) -> None:
    for name in (
        "subs.srt",
        "overlay.png",
        "music.wav",
        "intro.mp4",
        "outro.mp4",
        "second.mp4",
    ):
        (tmp_path / name).write_bytes(b"x")
    assets = tmp_path / "assets"
    assets.mkdir()
    recipe = parse_recipe(
        payload(
            steps=[
                {
                    "id": "subs",
                    "type": "transcribe",
                    "params": {"srt_path": str(tmp_path / "subs.srt")},
                },
                {
                    "id": "render",
                    "type": "shorts.render",
                    "params": {
                        "overlay_path": str(tmp_path / "overlay.png"),
                        "music_path": str(tmp_path / "music.wav"),
                        "intro_path": str(tmp_path / "intro.mp4"),
                        "outro_path": str(tmp_path / "outro.mp4"),
                        "second_source_path": str(tmp_path / "second.mp4"),
                    },
                },
                {
                    "id": "broll",
                    "type": "broll.plan",
                    "params": {"asset_dir": str(assets)},
                },
            ]
        )
    )

    resolved = resolve_recipe_paths(recipe, [tmp_path])

    assert resolved.steps[0].params["srt_path"] == str((tmp_path / "subs.srt").resolve())
    assert resolved.steps[1].params["music_path"] == str((tmp_path / "music.wav").resolve())
    assert resolved.steps[1].params["second_source_path"] == str(
        (tmp_path / "second.mp4").resolve()
    )
    assert resolved.steps[2].params["asset_dir"] == str(assets.resolve())


def test_save_user_recipe_keeps_bounded_history(tmp_path: Path) -> None:
    recipe = parse_recipe(payload())

    for _ in range(25):
        path = save_user_recipe(recipe)

    assert path.is_file()
    history = recipes.recipe_history_dir("mine")
    versions = sorted(history.glob("*.json"))
    assert len(versions) == 20
    assert list_recipe_history("mine")


def test_recipe_history_reports_versions_and_skips_bad_files() -> None:
    assert list_recipe_history("missing") == []

    history = recipes.recipe_history_dir("mine")
    history.mkdir(parents=True, exist_ok=True)
    (history / "1.json").write_text(json.dumps(payload()), encoding="utf-8")
    (history / "2.json").write_text("not json", encoding="utf-8")

    entries = list_recipe_history("mine")

    assert [entry["version"] for entry in entries] == ["1"]
    assert entries[0]["step_count"] == 1


def test_restore_recipe_version_requires_a_known_version() -> None:
    with pytest.raises(RecipeError, match="Unknown recipe version"):
        restore_recipe_version("mine", "999")

    history = recipes.recipe_history_dir("mine")
    history.mkdir(parents=True, exist_ok=True)
    (history / "1.json").write_text(json.dumps(payload()), encoding="utf-8")

    restored = restore_recipe_version("mine", "1")

    assert recipe_to_dict(restored)["id"] == "mine"
    assert (user_recipes_dir() / "mine.json").is_file()
