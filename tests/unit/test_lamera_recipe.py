from __future__ import annotations

from videoflow.application.recipe_meta import get_meta
from videoflow.core.recipe import parse_recipe
from videoflow.engine.recipes import get_recipe
from videoflow.steps import get_step, requirements_by_type, step_types
from videoflow.steps.ports import validate_recipe_ports


def test_lamera_recipe_is_valid_grouped_and_favorite() -> None:
    recipe = get_recipe("lamera_video_edit")
    recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
    validate_recipe_ports(recipe)
    resolved = recipe.with_variables({})
    for step in resolved.steps:
        get_step(step.type).validate_params(step.params)

    assert len(recipe.steps) == 65
    assert len(recipe.ui.groups) == 6
    step_ids = {step.id for step in recipe.steps}
    assert step_ids == set(recipe.ui.nodes)
    for group in recipe.ui.groups:
        assert group.label
        assert group.description
        assert group.color.startswith("#")
        assert set(group.nodes) <= step_ids
    assert get_meta("lamera_video_edit").favorite is True


def test_lamera_recipe_contains_the_documented_pipeline() -> None:
    recipe = get_recipe("lamera_video_edit")
    types = [step.type for step in recipe.steps]
    required = {
        "human.input",
        "human.files",
        "human.gate",
        "research.multi_agent",
        "research.consolidate",
        "presenter.profile",
        "script.dual_output",
        "ingest",
        "decoupage.calibrate",
        "vision.face_contact",
        "audio.vad",
        "transcribe",
        "retakes.cull",
        "edit.drift",
        "edit.timeline",
        "transcript.blocks",
        "entities.extract",
        "entities.apply",
        "style.guide",
        "storyboard.plan",
        "storyboard.units",
        "storyboard.preview",
        "assets.discover",
        "assets.harvest",
        "assets.license_audit",
        "assets.assign",
        "motion.codegen",
        "motion.render",
        "audio.master",
        "audio.compose",
        "sfx.synthesize",
        "audio.mix",
        "audio.qa",
        "intro.compile",
        "factcheck.audit",
        "voice.patch",
        "export.nle",
        "nle.qa",
        "export.video",
    }
    assert required <= set(types)
    assert types.count("research.multi_agent") == 4


def test_recipe_ui_groups_round_trip() -> None:
    recipe = parse_recipe(
        {
            "schema_version": 1,
            "id": "grouped",
            "name": "Grouped",
            "steps": [
                {"id": "one", "type": "ingest"},
                {"id": "two", "type": "audio.vad", "needs": ["one"]},
            ],
            "ui": {
                "version": 1,
                "nodes": {
                    "one": {"x": 10, "y": 20},
                    "two": {"x": 500, "y": 20},
                },
                "groups": [
                    {
                        "id": "phase",
                        "label": "Phase",
                        "description": "One phase",
                        "color": "#38bdf8",
                        "x": 0,
                        "y": 0,
                        "width": 1000,
                        "height": 300,
                        "nodes": ["one", "two"],
                    }
                ],
            },
        }
    )
    payload = recipe.model_dump(mode="json")
    restored = parse_recipe(payload)

    assert restored.ui.groups[0].label == "Phase"
    assert restored.ui.groups[0].nodes == ["one", "two"]
