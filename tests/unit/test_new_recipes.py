from __future__ import annotations

from videoflow.application.recipe_meta import get_meta
from videoflow.engine.recipes import get_recipe
from videoflow.steps import requirements_by_type, step_types
from videoflow.steps.ports import validate_recipe_ports


def _validate(recipe_id: str):
    recipe = get_recipe(recipe_id)
    recipe.validate_graph(
        step_types(), requires_by_type=requirements_by_type()
    )
    validate_recipe_ports(recipe)
    return recipe


def test_footage_intelligence_edit_is_complete_and_favorite() -> None:
    recipe = _validate("footage_intelligence_edit")
    types = {step.type for step in recipe.steps}
    gate_ids = {
        step.params.get("gate_id")
        for step in recipe.steps
        if step.type in {"human.gate", "human.input", "human.files"}
    }

    assert len(recipe.steps) == 55
    assert len(recipe.ui.groups) == 6
    assert {
        "ingest",
        "transcribe",
        "vision.ocr",
        "vision.segment",
        "vision.track",
        "motion.callout",
        "motion.attach",
        "export.video",
        "export.nle",
        "qa.frames",
        "qa.vision",
        "qa.repair",
    } <= types
    assert {
        "brief",
        "decoupage_review",
        "entities_review",
        "style_review",
        "units_review",
        "vision_review",
        "assets_review",
        "motion_review",
        "qa_review",
        "final_review",
    } <= gate_ids
    assert get_meta("footage_intelligence_edit").favorite is True
