"""Copilot proposals are validated against the domain rules."""

from __future__ import annotations

import pytest

from videoflow.application.copilot import propose_recipe, propose_timeline_edits
from videoflow.domain.errors import RecipeError, StateNotReadyError


class FakeClient:
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, prompt: str, schema_name: str):
        return self.payload


def test_recipe_proposal_is_validated() -> None:
    client = FakeClient(
        {
            "schema_version": 1,
            "id": "copilot_demo",
            "name": "Demo",
            "steps": [{"id": "ingest", "type": "ingest", "params": {}}],
        }
    )
    recipe = propose_recipe(client, "ingest a file")
    assert recipe.id == "copilot_demo"
    assert [step.type for step in recipe.steps] == ["ingest"]


def test_invalid_recipe_is_rejected() -> None:
    client = FakeClient(
        {"schema_version": 1, "id": "bad", "steps": [{"id": "x", "type": "nope"}]}
    )
    with pytest.raises(RecipeError):
        propose_recipe(client, "make something")


def test_timeline_edits_are_validated() -> None:
    clips = [{"id": "v1", "start_sec": 0, "end_sec": 2}]
    client = FakeClient(
        {
            "edits": [
                {
                    "clip_id": "v1",
                    "action": "trim",
                    "start_sec": 0.2,
                    "end_sec": 1.5,
                }
            ],
            "reasoning": "tighten",
        }
    )
    edits = propose_timeline_edits(client, "tighten", clips)
    assert edits[0]["action"] == "trim"


def test_unknown_clip_or_action_is_rejected() -> None:
    clips = [{"id": "v1", "start_sec": 0, "end_sec": 2}]
    with pytest.raises(StateNotReadyError):
        propose_timeline_edits(
            FakeClient({"edits": [{"clip_id": "nope", "action": "trim"}]}),
            "x",
            clips,
        )
    with pytest.raises(StateNotReadyError):
        propose_timeline_edits(
            FakeClient({"edits": [{"clip_id": "v1", "action": "explode"}]}),
            "x",
            clips,
        )
