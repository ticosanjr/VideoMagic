from __future__ import annotations

import json
from pathlib import Path

from videoflow.application.style_guide import default_style, merge_llm_style, render_markdown
from videoflow.core.context import PipelineContext
from videoflow.steps.art_direction import (
    StoryboardUnitsStep,
    StyleGuideParams,
    StyleGuideStep,
    UnitsParams,
)
from videoflow.steps.base import StepIO


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )


def test_default_style_and_merge() -> None:
    style = default_style("dark")
    assert style["palette"]
    assert "Typography" in render_markdown(style)
    merged = merge_llm_style(style, {"palette": ["#000000"], "rules": ["one"]})
    assert merged["palette"] == ["#000000"]
    assert merged["rules"] == ["one"]


def test_style_guide_step(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.metadata["hilt_answers"] = {
        "answers": {"visual_style": "paper dossier with red accents"}
    }
    StyleGuideStep().run(context, StyleGuideParams(), StepIO())
    style = context.metadata["style_guide"]
    assert style["palette"]
    assert (context.output / "style" / "style-guide.json").is_file()
    assert "paper" in (context.output / "style" / "style-guide.md").read_text().lower()


def test_storyboard_units_from_script(tmp_path: Path) -> None:
    context = _context(tmp_path)
    (context.output / "script").mkdir(parents=True)
    (context.output / "script" / "script.json").write_text(
        json.dumps(
            {
                "sections": [
                    {
                        "id": 1,
                        "title": "Document",
                        "narration": "The court record shows the deed.",
                        "visual": "Full screen document highlight with a lower third.",
                        "duration_sec": 45,
                    },
                    {
                        "id": 2,
                        "title": "Presenter",
                        "narration": "The presenter explains the finding.",
                        "visual": "Presenter close-up with a split screen.",
                        "duration_sec": 30,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    StoryboardUnitsStep().run(context, UnitsParams(), StepIO())
    units = context.metadata["storyboard_units"]
    assert len(units) == 2
    assert units[0]["layout"] == "lower_third"
    assert units[1]["layout"] == "presenter_split"
    assert units[1]["start_sec"] == 45.0
