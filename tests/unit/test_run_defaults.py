from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application.run_defaults import resolve_run_roots
from videoflow.core.recipe import parse_recipe
from videoflow.domain.errors import RecipeError


def test_source_and_workspace_come_from_nodes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    recipe = parse_recipe(
        {
            "schema_version": 1,
            "id": "defaults",
            "name": "Defaults",
            "steps": [
                {
                    "id": "ingest",
                    "type": "ingest",
                    "params": {"source": str(source)},
                }
            ],
        }
    )
    resolved_source, resolved_output = resolve_run_roots(
        recipe, None, None, [tmp_path]
    )
    assert resolved_source == source.resolve()
    assert resolved_output == (tmp_path / "clip-videoflow").resolve()


def test_missing_source_is_actionable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    recipe = parse_recipe(
        {
            "schema_version": 1,
            "id": "defaults",
            "name": "Defaults",
            "steps": [{"id": "ingest", "type": "ingest", "params": {}}],
        }
    )
    with pytest.raises(RecipeError, match="No input media"):
        resolve_run_roots(recipe, None, None, [tmp_path])


def test_script_first_recipe_gets_a_placeholder_source(tmp_path: Path) -> None:
    recipe = parse_recipe(
        {
            "schema_version": 1,
            "id": "synthetic",
            "name": "Synthetic",
            "steps": [
                {
                    "id": "brief",
                    "type": "human.input",
                    "params": {
                        "gate_id": "brief",
                        "questions": [{"id": "topic", "label": "Topic"}],
                    },
                }
            ],
        }
    )
    source, output = resolve_run_roots(
        recipe, None, str(tmp_path / "workspace"), [tmp_path]
    )
    assert output == (tmp_path / "workspace").resolve()
    assert source == output / ".script-source"
