"""Recipe validation, variable coercion, profiles, and file loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.core.recipe import (
    load_recipe,
    parse_recipe,
    recipe_to_dict,
)
from videoflow.domain.errors import RecipeError


def body(**overrides: object) -> dict:
    payload = {
        "schema_version": 1,
        "id": "valid",
        "name": "Valid",
        "steps": [{"id": "ingest", "type": "ingest"}],
    }
    payload.update(overrides)
    return payload


def test_ids_are_validated() -> None:
    with pytest.raises(RecipeError, match="recipe id must contain"):
        parse_recipe(body(id="bad id"))
    with pytest.raises(RecipeError, match="step id must start with a letter"):
        parse_recipe(body(steps=[{"id": "1bad", "type": "ingest"}]))


def test_graph_rejects_duplicates_self_deps_and_unknown_deps() -> None:
    duplicate = parse_recipe(
        body(
            steps=[
                {"id": "a", "type": "ingest"},
                {"id": "a", "type": "ingest"},
            ]
        )
    )
    with pytest.raises(RecipeError, match="Duplicate step ids"):
        duplicate.validate_graph({"ingest"})

    selfish = parse_recipe(
        body(steps=[{"id": "a", "type": "ingest", "needs": ["a"]}])
    )
    with pytest.raises(RecipeError, match="cannot depend on itself"):
        selfish.validate_graph({"ingest"})

    unknown = parse_recipe(
        body(steps=[{"id": "a", "type": "ingest", "needs": ["missing"]}])
    )
    with pytest.raises(RecipeError, match="needs unknown step"):
        unknown.validate_graph({"ingest"})


def test_disabled_dependencies_are_reported() -> None:
    recipe = parse_recipe(
        body(
            steps=[
                {"id": "a", "type": "ingest"},
                {"id": "b", "type": "audio.vad", "needs": ["a"], "enabled": False},
                {"id": "c", "type": "edit.timeline", "needs": ["b"]},
            ]
        )
    )

    with pytest.raises(RecipeError, match="disabled or missing"):
        recipe.topological_order()


def test_variables_are_coerced_and_validated() -> None:
    recipe = parse_recipe(
        body(
            variables={
                "count": {"type": "number"},
                "ratio": {"type": "number", "default": "2.5"},
                "flag": {"type": "boolean", "default": "yes"},
                "label": {"type": "string", "default": 12},
                "mode": {"type": "enum", "options": ["a", "b"], "default": "a"},
                "required": {"type": "string", "required": True},
            }
        )
    )

    resolved = recipe.resolved_variables({"count": "3", "required": "value"})

    assert resolved["count"] == 3
    assert resolved["ratio"] == 2.5
    assert resolved["flag"] is True
    assert resolved["label"] == "12"
    assert resolved["mode"] == "a"
    assert resolved["required"] == "value"


def test_invalid_variable_values_are_actionable() -> None:
    required = parse_recipe(
        body(variables={"name": {"type": "string", "required": True}})
    )
    with pytest.raises(RecipeError, match="is required"):
        required.resolved_variables()

    with pytest.raises(RecipeError, match="must be a number"):
        parse_recipe(body(variables={"n": {"type": "number"}})).resolved_variables({"n": "x"})

    with pytest.raises(RecipeError, match="must be one of"):
        parse_recipe(
            body(variables={"m": {"type": "enum", "options": ["a"]}})
        ).resolved_variables({"m": "z"})


def test_profiles_apply_variables_and_step_overrides() -> None:
    recipe = parse_recipe(
        body(
            variables={"speed": {"type": "string", "default": "slow"}},
            profiles={
                "fast": {
                    "variables": {"speed": "fast", "extra": {"type": "string", "default": "x"}},
                    "steps": {"ingest": {"engine": "ffmpeg"}},
                }
            },
            steps=[{"id": "ingest", "type": "ingest", "params": {}}],
        )
    )

    resolved = recipe.with_variables(profile="fast")

    assert resolved.variables_resolved["speed"] == "fast"
    assert resolved.variables_resolved["extra"] == "x"
    assert resolved.steps[0].params == {"engine": "ffmpeg"}

    with pytest.raises(RecipeError, match="Unknown recipe profile"):
        recipe.with_variables(profile="missing")


def test_uses_llm_detects_optional_steps() -> None:
    assert parse_recipe(body()).uses_llm() is False
    assert (
        parse_recipe(
            body(steps=[{"id": "retakes", "type": "retakes.cull"}])
        ).uses_llm()
        is True
    )
    assert (
        parse_recipe(
            body(
                steps=[
                    {
                        "id": "retakes",
                        "type": "retakes.cull",
                        "enabled": False,
                    }
                ]
            )
        ).uses_llm()
        is False
    )


def test_load_recipe_reports_file_errors(tmp_path: Path) -> None:
    with pytest.raises(RecipeError, match="Cannot read recipe"):
        load_recipe(tmp_path / "missing.json")

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not json", encoding="utf-8")
    with pytest.raises(RecipeError, match="not valid JSON"):
        load_recipe(invalid)

    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    with pytest.raises(RecipeError, match="root must be a JSON object"):
        load_recipe(array)


def test_load_recipe_and_serialise(tmp_path: Path) -> None:
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(body()), encoding="utf-8")

    recipe = load_recipe(path)
    payload = recipe_to_dict(recipe)

    assert recipe.id == "valid"
    assert payload["steps"][0]["id"] == "ingest"


def test_parse_recipe_reports_the_first_location() -> None:
    with pytest.raises(RecipeError, match="name"):
        parse_recipe(body(name=""))
