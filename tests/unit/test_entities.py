from __future__ import annotations

import json
from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.steps.base import StepIO
from videoflow.steps.entities import (
    EntityApplyParams,
    EntityApplyStep,
    EntityExtractParams,
    EntityExtractStep,
)


def test_entity_extract_builds_three_manifests_with_ranges(tmp_path: Path) -> None:
    output = tmp_path / "out"
    (output / "narrative").mkdir(parents=True)
    (output / "script").mkdir(parents=True)
    (output / "narrative" / "blocks.json").write_text(
        json.dumps(
            {
                "blocks": [
                    {
                        "context_block_id": "block_001",
                        "start_sec": 1.0,
                        "end_sec": 4.0,
                        "text": "Lula, Cerveró and the Guarujá triplex, R$ 10 milhões.",
                    },
                    {
                        "context_block_id": "block_002",
                        "start_sec": 5.0,
                        "end_sec": 8.0,
                        "text": "The same Cerveró case returns in court.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (output / "script" / "edition.md").write_text(
        'Lula and Nestor Cerveró appear in the "Guarujá triplex" section.',
        encoding="utf-8",
    )
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )

    EntityExtractStep().run(context, EntityExtractParams(), StepIO())

    manifest = json.loads(
        (output / "narrative" / "entities.json").read_text(encoding="utf-8")
    )
    assert manifest["counts"]["people"] >= 1
    people = {item["canonical_name"]: item for item in manifest["people"]}
    assert "Nestor Cerveró" in people
    assert "Lula" in people
    assert people["Nestor Cerveró"]["block_ids"] == ["block_001", "block_002"]
    assert people["Nestor Cerveró"]["start_sec"] == 1.0
    assert people["Nestor Cerveró"]["end_sec"] == 8.0
    events = {item["name"] for item in manifest["objects_locations_events"]}
    assert "Guarujá triplex" in events
    assert manifest["counts"]["data_metrics"] >= 1
    assert any(
        "10" in item["raw_value"] for item in manifest["data_metrics"]
    )


def test_entity_corrections_replace_names_and_copy_manifest(tmp_path: Path) -> None:
    output = tmp_path / "out"
    narrative = output / "narrative"
    narrative.mkdir(parents=True)
    (narrative / "entities.json").write_text(
        json.dumps(
            {
                "blocks": [
                    {
                        "extracted_entities": {
                            "people": [{"raw_mention": "severó"}],
                            "physical_objects": [{"object": "triplex"}],
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (output / "entities").mkdir()
    (output / "entities" / "corrections.json").write_text(
        json.dumps(
            {
                "answers": {
                    "people_corrections": "severó -> Nestor Cerveró",
                    "visual_corrections": "triplex => Guarujá triplex",
                }
            }
        ),
        encoding="utf-8",
    )
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )
    EntityApplyStep().run(context, EntityApplyParams(), StepIO())
    corrected = json.loads(
        (narrative / "entities-corrected.json").read_text(encoding="utf-8")
    )
    text = corrected["blocks"][0]["extracted_entities"]
    assert text["people"][0]["raw_mention"] == "Nestor Cerveró"
    assert text["physical_objects"][0]["object"] == "Guarujá triplex"
    assert context.metadata["entity_corrections"]["corrected_count"] == 2


def test_entity_helper_functions() -> None:
    from videoflow.steps import entities

    mappings = entities._mappings(
        {
            "people_corrections": "A -> B\n# skip\nbad line\nC|D",
            "visual_corrections": "E => F",
        }
    )
    assert mappings == {"A": "B", "C": "D", "E": "F"}
    assert entities._replace("A C", mappings) == "B D"
    assert entities._replace(["A"], mappings) == ["B"]
    assert entities._replace({"x": "C"}, mappings) == {"x": "D"}
    assert entities._replace(1, mappings) == 1

    assert entities._block_items({"blocks": [{"id": 1}, "x"]}) == [{"id": 1}]
    assert entities._block_items({}) == []
    names = entities._script_names("Alice went to Paris with Bob")
    assert "Alice" in names and "Paris" in names
    assert entities._canonical_name("alice", names) == "Alice"
    assert entities._canonical_name("unknown", names) == "unknown"

    entry = entities._entry("Alice", kind="person")
    entities._add_block_range(entry, {"context_block_id": "b1", "start_sec": 2, "end_sec": 4})
    entities._add_block_range(entry, {"context_block_id": "b2", "start_sec": 1, "end_sec": 5})
    assert entry["block_ids"] == ["b1", "b2"]
    assert entry["start_sec"] == 1 and entry["end_sec"] == 5
    assert entities._sorted({"a": entry}, 10) == [entry]


def test_deterministic_and_model_entities() -> None:
    from videoflow.steps import entities

    blocks = [
        {
            "context_block_id": "b1",
            "text": "Alice met Bob in Paris and raised 25%.",
            "start_sec": 0,
            "end_sec": 4,
        }
    ]
    people, objects, metrics = entities._deterministic_entities(
        blocks, ["Alice", "Bob"]
    )
    assert people["alice"]["kind"] == "person"
    assert people["alice"]["block_ids"] == ["b1"]
    assert objects or metrics

    payload = {
        "people": [
            {
                "canonical_name": "alice",
                "raw_mentions": ["Alice"],
                "block_ids": ["b1"],
            }
        ],
        "objects_locations_events": [
            {"name": "Paris", "kind": "location", "block_ids": ["b1"]}
        ],
        "data_metrics": [
            {"raw_value": "25%", "formatted_display": "25%", "block_ids": ["b1"]}
        ],
    }
    entities._merge_model_entities(
        people,
        objects,
        metrics,
        payload,
        {"b1": blocks[0]},
        ["Alice"],
    )
    assert people["alice"]["raw_mentions"][0] == "Alice"
    assert objects["paris"]["block_ids"] == ["b1"]
    assert metrics["25%"]["formatted_display"] == "25%"


def test_entity_extract_handles_missing_files_and_bad_model(
    tmp_path: Path, monkeypatch
) -> None:
    output = tmp_path / "out"
    (output / "narrative").mkdir(parents=True)
    (output / "narrative" / "blocks.json").write_text(
        json.dumps(
            {
                "blocks": [
                    {
                        "context_block_id": "b1",
                        "start_sec": 0,
                        "end_sec": 2,
                        "text": "Alice Smith raised 25%.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (output / "narrative" / "blocks.json").write_text("{bad", encoding="utf-8")
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )
    context.metadata["narrative_entities"] = {}
    EntityExtractStep().run(
        context,
        EntityExtractParams(
            script_path="script/missing.md", known_entities=["Alice Smith"]
        ),
        StepIO(),
    )
    assert context.metadata["narrative_entities"]["counts"]["objects_locations_events"] >= 1

    (output / "narrative" / "blocks.json").write_text(
        json.dumps(
            {
                "blocks": [
                    {
                        "context_block_id": "b1",
                        "start_sec": 0,
                        "end_sec": 2,
                        "text": "Alice spoke about the launch.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    class GoodClient:
        def complete_json(self, prompt, schema):
            return {
                "people": [
                    "bad",
                    {"canonical_name": "", "raw_mentions": ["ignored"]},
                    {
                        "canonical_name": "alice",
                        "raw_mentions": ["Alice", "Alice"],
                        "block_ids": ["b1", "missing"],
                    },
                ],
                "objects_locations_events": [
                    "bad",
                    {"name": "", "kind": "object"},
                    {"name": "Launch", "kind": "event", "block_ids": ["b1"]},
                ],
                "data_metrics": [
                    "bad",
                    {"raw_value": ""},
                    {"raw_value": "25%", "block_ids": ["b1"]},
                ],
            }

    EntityExtractStep().run(
        context, EntityExtractParams(), StepIO(llm_client=GoodClient())
    )
    manifest = context.metadata["narrative_entities"]
    assert any(
        item["canonical_name"].casefold() == "alice" for item in manifest["people"]
    )
    assert any(item["name"] == "Launch" for item in manifest["objects_locations_events"])

    class BadClient:
        def complete_json(self, prompt, schema):
            raise RuntimeError("model down")

    EntityExtractStep().run(
        context, EntityExtractParams(), StepIO(llm_client=BadClient())
    )
    assert any("Entity model fallback" in item for item in context.warnings)

    assert EntityExtractStep().cache_outputs(context)


def test_entity_apply_without_manifest_and_corrections(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )
    EntityApplyStep().run(context, EntityApplyParams(), StepIO())
    markdown = output / "narrative" / "entities-corrected.md"
    assert "No corrections were supplied." in markdown.read_text(encoding="utf-8")
    assert EntityApplyStep().cache_outputs(context)
    assert EntityExtractStep().cache_outputs(
        PipelineContext(
            source=tmp_path / "s.mp4",
            output=output,
            work=output / "work",
            exports=output / "exports",
        )
    ) == ()


def test_entity_merge_ignores_empty_values() -> None:
    from videoflow.steps import entities

    people = {
        "alice": {
            **entities._entry("Alice", kind="person"),
            "raw_mentions": ["Alice"],
        }
    }
    objects: dict = {}
    metrics: dict = {}
    entities._merge_model_entities(
        people,
        objects,
        metrics,
        {
            "people": [{"canonical_name": "Alice", "raw_mentions": ["Alice", "A."]}],
            "objects_locations_events": [{"name": "Paris", "kind": "location"}],
            "data_metrics": [{"raw_value": "25%"}],
        },
        {},
        ["Alice"],
    )
    assert people["alice"]["raw_mentions"] == ["Alice", "A."]
    assert objects["paris"]["kind"] == "location"
    assert metrics["25%"]["formatted_display"] == "25%"
