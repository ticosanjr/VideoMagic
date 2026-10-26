"""Runner isolation: domain state only crosses steps through declared ports."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tests.unit.test_runner_checkpoints import context
from videoflow.core.recipe import parse_recipe
from videoflow.engine.runner import RecipeRunner


def runner() -> RecipeRunner:
    recipe = parse_recipe(
        {
            "schema_version": 1,
            "id": "isolation",
            "name": "Isolation",
            "steps": [{"id": "ingest", "type": "ingest", "params": {}}],
        }
    )
    return RecipeRunner(recipe)


def test_ambient_domain_state_does_not_leak(tmp_path: Path) -> None:
    parent = context(tmp_path)
    step_context = parent.model_copy(deep=True)
    step_context.metadata["secret"] = "must not leak"
    step_context.artifacts["secret.bin"] = "/tmp/secret.bin"
    step_context.shorts = [{"title": "leak"}]
    step_context.selected_shorts = [{"title": "leak"}]
    step_context.short_captions["leak"] = "/tmp/leak.ass"
    step_context.warnings.append("visible warning")
    step_context.hashes["fake"] = "hash"
    step = SimpleNamespace(output_ports=[])

    runner()._merge_step_outputs(parent, step_context, step, SimpleNamespace(id="fake"))

    assert "secret" not in parent.metadata
    assert "secret.bin" not in parent.artifacts
    assert parent.shorts == []
    assert parent.selected_shorts == []
    assert parent.short_captions == {}
    assert "visible warning" in parent.warnings
    assert parent.hashes["fake"] == "hash"


def test_declared_metadata_port_copies_only_that_key(tmp_path: Path) -> None:
    parent = context(tmp_path)
    step_context = parent.model_copy(deep=True)
    step_context.metadata["broll_plan"] = {"Short": []}
    step_context.metadata["secret"] = "must not leak"
    step = SimpleNamespace(
        output_ports=[
            SimpleNamespace(id="plan", context_key="metadata:broll_plan")
        ]
    )

    runner()._merge_step_outputs(parent, step_context, step, SimpleNamespace(id="fake"))

    assert parent.metadata["broll_plan"] == {"Short": []}
    assert "secret" not in parent.metadata
