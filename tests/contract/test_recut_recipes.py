from __future__ import annotations

from videoflow.engine.recipes import get_recipe
from videoflow.steps import requirements_by_type, step_types


def test_recut_replacement_is_a_valid_silence_only_recipe() -> None:
    recipe = get_recipe("recut_replacement")
    recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
    enabled = recipe.enabled_steps()
    assert [step.id for step in enabled] == ["ingest", "vad", "timeline", "export"]
    assert "transcribe" not in {step.id for step in enabled}
    timeline = next(step for step in enabled if step.id == "timeline")
    assert timeline.params["cut_mode"] == "$cut_mode"
    export = next(step for step in enabled if step.id == "export")
    assert export.params["targets"] == ["mp4", "resolve", "premiere", "kdenlive"]


def test_recut_retakes_variant_adds_transcription_and_culling() -> None:
    recipe = get_recipe("recut_replacement_retakes")
    recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
    assert [step.id for step in recipe.enabled_steps()] == [
        "ingest",
        "vad",
        "transcribe",
        "retakes",
        "timeline",
        "export",
    ]
    timeline = next(step for step in recipe.enabled_steps() if step.id == "timeline")
    assert "retakes" in timeline.needs


def test_recut_variables_apply_and_default_to_hard_cuts() -> None:
    recipe = get_recipe("recut_replacement")
    resolved = recipe.with_variables(
        {
            "cut_mode": "j_cut",
            "min_silence_ms": 500,
            "spike_suppression_ms": 240,
            "merge_gap_ms": 80,
            "pad_before_ms": 40,
            "pad_after_ms": 90,
        }
    )
    vad = next(step for step in resolved.enabled_steps() if step.id == "vad")
    timeline = next(step for step in resolved.enabled_steps() if step.id == "timeline")
    assert vad.params["min_silence_ms"] == 500
    assert vad.params["spike_suppression_ms"] == 240
    assert vad.params["merge_gap_ms"] == 80
    assert vad.params["pad_before_ms"] == 40
    assert vad.params["pad_after_ms"] == 90
    assert timeline.params["cut_mode"] == "j_cut"
