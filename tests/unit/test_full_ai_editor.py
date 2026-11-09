from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application import recipe_meta
from videoflow.domain.errors import HumanInputRequiredError
from videoflow.engine.recipes import get_recipe
from videoflow.engine.runner import RecipeRunner
from videoflow.steps import requirements_by_type, step_types
from videoflow.steps.ports import validate_recipe_ports


def test_full_ai_editor_is_valid_and_favorite() -> None:
    recipe = get_recipe("full_ai_editor")
    recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
    validate_recipe_ports(recipe)
    assert recipe.name == "Full AI Editor"
    assert recipe_meta.get_meta("full_ai_editor").favorite is True
    ids = [step.id for step in recipe.topological_order()]
    assert ids[0] == "brief"
    assert ids.index("ingest") < ids.index("timeline")
    assert ids.index("final_review") < ids.index("export")


def test_full_ai_editor_pauses_at_the_brief(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    recipe = get_recipe("full_ai_editor")
    with pytest.raises(HumanInputRequiredError) as raised:
        RecipeRunner(recipe).run(source, tmp_path / "out", resume=False)
    interaction = raised.value.interaction
    assert interaction["gate_id"] == "brief"
    assert interaction["kind"] == "question"
    assert {item["id"] for item in interaction["questions"]} >= {
        "topic",
        "temporal_scope",
        "presenter_profile",
    }
