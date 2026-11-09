from __future__ import annotations

import json
from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.steps.base import StepIO
from videoflow.steps.entities import EntityApplyParams, EntityApplyStep


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
