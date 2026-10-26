"""Port wiring validation and context read/write helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.core.recipe import parse_recipe
from videoflow.domain.errors import RecipeError
from videoflow.steps import ports
from videoflow.steps.ports import (
    apply_inputs,
    digest_value,
    ports_for_type,
    read_context,
    validate_recipe_ports,
    write_context,
)


def recipe(steps: list[dict], **overrides: object) -> object:
    return parse_recipe(
        {
            "schema_version": 1,
            "id": "ports",
            "name": "Ports",
            "steps": steps,
            **overrides,
        }
    )


def validate(steps: list[dict], **overrides: object) -> None:
    validate_recipe_ports(recipe(steps, **overrides))


def test_unknown_input_port_is_rejected() -> None:
    with pytest.raises(RecipeError, match="unknown input port"):
        validate(
            [
                {"id": "ingest", "type": "ingest"},
                {
                    "id": "edit",
                    "type": "edit.timeline",
                    "needs": ["ingest"],
                    "inputs": {"nope": "ingest.media"},
                },
            ]
        )


def test_references_need_node_and_port_syntax() -> None:
    with pytest.raises(RecipeError, match="expected node.port"):
        validate(
            [
                {"id": "ingest", "type": "ingest"},
                {
                    "id": "edit",
                    "type": "edit.timeline",
                    "needs": ["ingest"],
                    "inputs": {"speech": "ingest"},
                },
            ]
        )


def test_unknown_source_nodes_and_ports_are_rejected() -> None:
    with pytest.raises(RecipeError, match="unknown node"):
        validate(
            [
                {"id": "ingest", "type": "ingest"},
                {
                    "id": "edit",
                    "type": "edit.timeline",
                    "needs": ["ingest"],
                    "inputs": {"speech": "missing.media"},
                },
            ]
        )

    with pytest.raises(RecipeError, match="unknown output"):
        validate(
            [
                {"id": "ingest", "type": "ingest"},
                {
                    "id": "edit",
                    "type": "edit.timeline",
                    "needs": ["ingest"],
                    "inputs": {"speech": "ingest.notaport"},
                },
            ]
        )


def test_sources_must_run_earlier_and_be_ancestors() -> None:
    with pytest.raises(RecipeError, match="must run earlier"):
        validate(
            [
                {"id": "ingest", "type": "ingest"},
                {
                    "id": "edit",
                    "type": "edit.timeline",
                    "needs": ["ingest"],
                    "inputs": {"speech": "later.speech"},
                },
                {
                    "id": "later",
                    "type": "audio.vad",
                    "needs": ["edit"],
                    "inputs": {"media": "ingest.media"},
                },
            ]
        )

    with pytest.raises(RecipeError, match="add ingest to needs"):
        validate(
            [
                {"id": "ingest", "type": "ingest"},
                {"id": "other", "type": "audio.vad"},
                {
                    "id": "edit",
                    "type": "edit.timeline",
                    "needs": ["other"],
                    "inputs": {"speech": "ingest.media"},
                },
            ]
        )


def test_types_must_match_and_required_inputs_must_be_wired() -> None:
    with pytest.raises(RecipeError, match="type mismatch"):
        validate(
            [
                {"id": "ingest", "type": "ingest"},
                {
                    "id": "edit",
                    "type": "edit.timeline",
                    "needs": ["ingest"],
                    "inputs": {"speech": "ingest.digest"},
                },
            ]
        )

    with pytest.raises(RecipeError, match="missing required inputs"):
        validate(
            [
                {"id": "ingest", "type": "ingest"},
                {
                    "id": "transcribe",
                    "type": "transcribe",
                    "needs": ["ingest"],
                    "inputs": {"media": "ingest.media"},
                },
                {
                    "id": "edit",
                    "type": "edit.timeline",
                    "needs": ["transcribe"],
                    "inputs": {"transcript": "transcribe.transcript"},
                },
            ]
        )


def test_paths_are_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))

    with pytest.raises(RecipeError, match="media override is not a file"):
        validate(
            [
                {
                    "id": "ingest",
                    "type": "ingest",
                    "media_override": str(tmp_path / "missing.mp4"),
                }
            ]
        )

    with pytest.raises(RecipeError, match="output folder is required"):
        validate(
            [
                {
                    "id": "ingest",
                    "type": "ingest",
                    "output_mode": "folder",
                }
            ]
        )


def test_read_and_write_context_handle_maps() -> None:
    context = SimpleNamespace(
        artifacts={"a": "path"},
        metadata={"m": 2},
        media="info",
    )

    assert read_context(context, "artifacts:a") == "path"
    assert read_context(context, "metadata:m") == 2
    assert read_context(context, "media") == "info"
    assert read_context(context, "missing") is None

    write_context(context, "artifacts:b", "two")
    write_context(context, "metadata:n", 3)
    write_context(context, "media", "new")
    assert context.artifacts["b"] == "two"
    assert context.metadata["n"] == 3
    assert context.media == "new"


def test_apply_inputs_reports_missing_sources() -> None:
    step = SimpleNamespace(
        input_ports=[SimpleNamespace(id="media", context_key="media")]
    )
    context = SimpleNamespace(port_outputs={}, media=None)
    with pytest.raises(RecipeError, match="has not produced"):
        apply_inputs(context, step, {"media": "ingest.media"})

    context.port_outputs["ingest"] = {}
    with pytest.raises(RecipeError, match="is missing"):
        apply_inputs(context, step, {"media": "ingest.media"})

    context.port_outputs["ingest"] = {"media": "info"}
    apply_inputs(context, step, {"media": "ingest.media"})
    assert context.media == "info"


def test_digest_value_handles_unserialisable_objects() -> None:
    class Opaque:
        def __repr__(self) -> str:
            return "opaque"

    assert digest_value({"a": 1}) == digest_value({"a": 1})
    assert digest_value(Opaque()) == digest_value(Opaque())


def test_unknown_step_types_have_no_ports() -> None:
    assert ports_for_type("unknown.step") == ((), ())
    assert ports.type_compatible("any", "string") is True
    assert ports.type_compatible("string", "media") is False
