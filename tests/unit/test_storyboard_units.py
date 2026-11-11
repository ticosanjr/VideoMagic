from __future__ import annotations

import json
from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.steps.art_direction import StoryboardUnitsStep, UnitsParams
from videoflow.steps.base import StepIO


def test_storyboard_units_merge_to_the_target_count(tmp_path: Path) -> None:
    output = tmp_path / "out"
    (output / "script").mkdir(parents=True)
    (output / "style").mkdir(parents=True)
    (output / "script" / "script.json").write_text(
        json.dumps(
            {
                "sections": [
                    {
                        "id": 1,
                        "title": "One",
                        "narration": "First part.",
                        "visual": "Presenter with document.",
                        "duration_sec": 10,
                    },
                    {
                        "id": 2,
                        "title": "Two",
                        "narration": "Second part.",
                        "visual": "Full screen motion graphic.",
                        "duration_sec": 10,
                    },
                    {
                        "id": 3,
                        "title": "Three",
                        "narration": "Third part.",
                        "visual": "Lower third.",
                        "duration_sec": 10,
                    },
                    {
                        "id": 4,
                        "title": "Four",
                        "narration": "Fourth part.",
                        "visual": "Presenter split.",
                        "duration_sec": 10,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (output / "style" / "style-guide.json").write_text(
        json.dumps({"palette": ["#080B10", "#F8FAFC", "#FF3B30"]}),
        encoding="utf-8",
    )
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )

    StoryboardUnitsStep().run(
        context,
        UnitsParams(max_units=10, max_unit_seconds=20, target_units=2),
        StepIO(),
    )

    units = context.metadata["storyboard_units"]
    assert len(units) == 2
    assert units[0]["title"] == "One +1"
    assert units[1]["title"] == "Three +1"
    assert units[0]["duration_sec"] == 20
    assert units[1]["duration_sec"] == 20
    assert "First part." in units[0]["narration"]
    assert "Second part." in units[0]["narration"]
    assert units[0]["asset_query"]
