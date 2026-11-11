from __future__ import annotations

import json
from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.steps.base import StepIO
from videoflow.steps.storyboard_preview import (
    StoryboardPreviewParams,
    StoryboardPreviewStep,
)


def test_storyboard_preview_selects_one_unit_per_layout(tmp_path: Path) -> None:
    output = tmp_path / "out"
    (output / "storyboard").mkdir(parents=True)
    (output / "style").mkdir(parents=True)
    units = [
        {
            "unit_id": "UNIT-0001",
            "title": "Full",
            "layout": "full_screen",
            "duration_sec": 30,
        },
        {
            "unit_id": "UNIT-0002",
            "title": "Lower",
            "layout": "lower_third",
            "duration_sec": 30,
        },
        {
            "unit_id": "UNIT-0003",
            "title": "Split",
            "layout": "presenter_split",
            "duration_sec": 30,
        },
        {
            "unit_id": "UNIT-0004",
            "title": "Presenter",
            "layout": "presenter_visual",
            "duration_sec": 30,
        },
    ]
    (output / "storyboard" / "units.json").write_text(
        json.dumps({"units": units}), encoding="utf-8"
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

    StoryboardPreviewStep().run(
        context,
        StoryboardPreviewParams(render=False, duration_sec=12),
        StepIO(),
    )

    payload = json.loads(
        (output / "storyboard" / "previews.json").read_text(encoding="utf-8")
    )
    assert payload["count"] == 4
    assert [item["layout"] for item in payload["previews"]] == [
        "full_screen",
        "lower_third",
        "presenter_split",
        "presenter_visual",
    ]
    assert all(item["duration_sec"] == 12 for item in payload["previews"])
    assert all(item["path"] == "" for item in payload["previews"])
    assert context.artifacts["storyboard_previews"].endswith("storyboard/previews.json")
