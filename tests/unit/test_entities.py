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
