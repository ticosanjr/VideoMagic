from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.core.recipe import parse_recipe
from videoflow.domain.errors import RecipeError
from videoflow.engine import runner as runner_module
from videoflow.engine.runner import RecipeRunner
from videoflow.steps import requirements_by_type, step_types
from videoflow.steps.audio import VadParams
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.ports import ports_for_type, validate_recipe_ports
from videoflow.steps.timeline import TimelineParams


def test_every_builtin_step_declares_ports() -> None:
    from videoflow.steps import iter_steps
    from videoflow.steps.ports import PORTS

    builtin = {
        step.type
        for step in iter_steps()
        if step.__class__.__module__.startswith("videoflow.steps")
    }
    assert sorted(builtin - set(PORTS)) == []


def test_core_ports_are_declared() -> None:
    vad_in, vad_out = ports_for_type("audio.vad")
    timeline_in, timeline_out = ports_for_type("edit.timeline")
    assert {port.id for port in vad_out} == {"speech", "engine"}
    assert {port.id for port in timeline_in} == {"speech", "transcript"}
    assert timeline_out[0].type == "timeline"
    assert vad_in[0].type == "media"


def _validate(recipe: dict) -> None:
    parsed = parse_recipe(recipe)
    parsed.validate_graph(step_types(), requires_by_type=requirements_by_type())
    validate_recipe_ports(parsed)


def test_ports_validate_compatibility_and_required_inputs() -> None:
    valid = {
        "schema_version": 1,
        "id": "ports",
        "name": "Ports",
        "steps": [
            {"id": "ingest", "type": "ingest", "params": {}},
            {"id": "vad", "type": "audio.vad", "needs": ["ingest"], "params": {}},
            {
                "id": "timeline",
                "type": "edit.timeline",
                "needs": ["vad"],
                "inputs": {"speech": "vad.speech"},
                "params": {},
            },
        ],
    }
    _validate(valid)

    mismatch = {
        **valid,
        "steps": [
            *valid["steps"][:2],
            {
                "id": "timeline",
                "type": "edit.timeline",
                "needs": ["vad"],
                "inputs": {"speech": "vad.engine"},
                "params": {},
            },
        ],
    }
    with pytest.raises(RecipeError, match="type mismatch"):
        _validate(mismatch)

    missing = {
        **valid,
        "steps": [
            *valid["steps"][:2],
            {
                "id": "timeline",
                "type": "edit.timeline",
                "needs": ["vad"],
                "inputs": {"transcript": "vad.speech"},
                "params": {},
            },
        ],
    }
    with pytest.raises(RecipeError, match="unknown output|type mismatch|missing required"):
        _validate(missing)


def test_runner_feeds_two_branches_from_two_vads(monkeypatch, tmp_path: Path) -> None:
    class FakeIngest(BaseStep):
        type = "ingest"
        params_model = VadParams

        def run(self, context, params, io: StepIO) -> None:
            context.media = None
            context.pcm_digest = "digest"

    class FakeVad(BaseStep):
        type = "audio.vad"
        params_model = VadParams

        def run(self, context, params, io: StepIO) -> None:
            value = int(params.min_silence_ms)
            context.speech_intervals = [(value, value + 1000)]

    class FakeTimeline(BaseStep):
        type = "edit.timeline"
        params_model = TimelineParams

        def run(self, context, params, io: StepIO) -> None:
            context.metadata[f"seen_{io.stage}"] = list(context.speech_intervals)
            context.state = None

    fake = {
        "ingest": FakeIngest(),
        "audio.vad": FakeVad(),
        "edit.timeline": FakeTimeline(),
    }
    monkeypatch.setattr(runner_module, "get_step", lambda step_type: fake[step_type])
    recipe = parse_recipe(
        {
            "schema_version": 1,
            "id": "branches",
            "name": "Branches",
            "steps": [
                {"id": "ingest", "type": "ingest", "params": {}},
                {
                    "id": "vad_a",
                    "type": "audio.vad",
                    "needs": ["ingest"],
                    "params": {"min_silence_ms": 100},
                },
                {
                    "id": "vad_b",
                    "type": "audio.vad",
                    "needs": ["ingest"],
                    "params": {"min_silence_ms": 300},
                },
                {
                    "id": "timeline_a",
                    "type": "edit.timeline",
                    "needs": ["vad_a"],
                    "inputs": {"speech": "vad_a.speech"},
                    "params": {},
                },
                {
                    "id": "timeline_b",
                    "type": "edit.timeline",
                    "needs": ["vad_b"],
                    "inputs": {"speech": "vad_b.speech"},
                    "params": {},
                },
            ],
        }
    )
    result = RecipeRunner(recipe).run(
        tmp_path / "source.mp4", tmp_path / "out", resume=False
    )
    assert result.context.metadata["seen_timeline_a"] == [(100, 1100)]
    assert result.context.metadata["seen_timeline_b"] == [(300, 1300)]
    assert result.context.port_outputs["vad_a"]["speech"] == [(100, 1100)]
    assert result.context.port_outputs["vad_b"]["speech"] == [(300, 1300)]
