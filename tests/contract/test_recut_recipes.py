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
    assert timeline.params["cut_mode"] == "hard"
    assert timeline.inputs == {"speech": "vad.speech"}
    export = next(step for step in recipe.enabled_steps() if step.id == "export")
    assert export.inputs == {"timeline": "timeline.timeline"}
    export = next(step for step in recipe.enabled_steps() if step.id == "export")
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


def test_recut_defaults_live_inside_the_nodes() -> None:
    from videoflow.steps import get_step

    recipe = get_recipe("recut_replacement")
    assert recipe.variables == {}
    for step in recipe.enabled_steps():
        get_step(step.type).validate_params(step.params)
    vad = next(step for step in recipe.enabled_steps() if step.id == "vad")
    timeline = next(step for step in recipe.enabled_steps() if step.id == "timeline")
    assert vad.params["apply_pads"] is False
    assert vad.params["min_silence_ms"] == 350
    assert vad.params["spike_suppression_ms"] == 180
    assert vad.params["merge_gap_ms"] == 120
    assert timeline.params["cut_mode"] == "hard"
    assert timeline.inputs == {"speech": "vad.speech"}
    export = next(step for step in recipe.enabled_steps() if step.id == "export")
    assert export.inputs == {"timeline": "timeline.timeline"}
    assert timeline.params["offset_ms"] == 200
    assert timeline.params["audio_crossfade_ms"] == 20


def test_api_validate_resolves_variables_before_step_validation(monkeypatch) -> None:
    from tests.contract.test_api_timeline import _client

    recipe = {
        "schema_version": 1,
        "id": "variable_recipe",
        "name": "Variable recipe",
        "variables": {
            "min_silence_ms": {"type": "number", "default": 280},
            "pad_ms": {"type": "number", "default": 40},
        },
        "steps": [
            {"id": "ingest", "type": "ingest", "params": {"extract_pcm": True}},
            {
                "id": "vad",
                "type": "audio.vad",
                "needs": ["ingest"],
                "params": {
                    "min_silence_ms": "$min_silence_ms",
                    "pad_before_ms": "$pad_ms",
                    "pad_after_ms": "$pad_ms",
                },
            },
        ],
    }
    client, _manager = _client(monkeypatch, __import__("pathlib").Path("/tmp/videoflow-vars"))
    response = client.post("/api/v1/recipes/validate", json=recipe)
    assert response.status_code == 200, response.text
    resolved = next(
        step for step in response.json()["resolved"]["steps"] if step["id"] == "vad"
    )
    assert resolved["params"]["min_silence_ms"] == 280
    assert resolved["params"]["pad_before_ms"] == 40


def test_recut_global_presets_are_valid_and_tuned() -> None:
    from videoflow.steps import get_step

    expected = {
        "recut_podcast": "j_cut",
        "recut_lecture": "hard",
        "recut_social": "l_cut",
    }
    for recipe_id, cut_mode in expected.items():
        recipe = get_recipe(recipe_id)
        recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
        for step in recipe.enabled_steps():
            get_step(step.type).validate_params(step.params)
        timeline = next(
            step for step in recipe.enabled_steps() if step.id == "timeline"
        )
        assert timeline.params["cut_mode"] == cut_mode
        assert recipe.variables == {}
        assert next(
            step for step in recipe.enabled_steps() if step.id == "export"
        ).params["targets"] == ["mp4", "resolve", "premiere", "kdenlive"]


def test_run_route_resolves_source_and_output_from_the_recipe(monkeypatch, tmp_path) -> None:
    from tests.contract.test_api_timeline import _client

    client, manager = _client(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    recipe = {
        "schema_version": 1,
        "id": "auto_roots",
        "name": "Auto roots",
        "steps": [
            {
                "id": "ingest",
                "type": "ingest",
                "params": {"source": str(source)},
            }
        ],
    }
    response = client.post(
        "/api/v1/recipes/run",
        json={"recipe": recipe, "source": "", "output": ""},
    )
    assert response.status_code == 202, response.text
    job = manager.get(response.json()["job"]["job_id"])
    assert str(job.source) == str(source.resolve())
    assert job.output.name == "source-videoflow"
