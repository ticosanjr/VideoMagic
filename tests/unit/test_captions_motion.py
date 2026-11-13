from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.application.captions import CaptionLine
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError
from videoflow.domain.state import MediaInfo, Sentence
from videoflow.steps.base import StepIO
from videoflow.steps.captions import (
    CaptionsPlanParams,
    CaptionsPlanStep,
    _split_line,
)
from videoflow.steps.motion_attach import (
    CompositeMatteParams,
    CompositeMatteStep,
    MotionCalloutParams,
    MotionCalloutStep,
)
from videoflow.steps.storyboard_timed import (
    StoryboardTimedStep,
    TimedUnitsParams,
    _merge_units,
    _word_events,
)


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    output.mkdir()
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )


def test_split_line_keeps_short_and_splits_long() -> None:
    short = CaptionLine(start=0, end=2, text="hello")
    assert _split_line(short, 40) == [short]
    long = CaptionLine(start=0, end=4, text="one two three four five six")
    parts = _split_line(long, 12)
    assert len(parts) > 1
    assert parts[0].start == 0
    assert parts[-1].end == 4


def test_captions_plan_disabled_and_empty(tmp_path: Path) -> None:
    context = _context(tmp_path)
    CaptionsPlanStep().run(context, CaptionsPlanParams(enabled=False), StepIO())
    assert context.metadata["captions_disabled"] is True

    CaptionsPlanStep().run(context, CaptionsPlanParams(), StepIO())
    assert any("transcript is empty" in item for item in context.warnings)


def test_captions_plan_merges_titles(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.media = MediaInfo(
        source_path=str(context.source),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=48000,
    )
    context.transcript = [
        Sentence(id=0, start_sample=0, end_sample=48000, text="hello world")
    ]
    (context.output / "titles.ass").write_text(
        "[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize\nStyle: Title,Arial,64\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 1,0:00:00.00,0:00:02.00,Title,,0,0,0,,"
        "Intro\n",
        encoding="utf-8",
    )
    CaptionsPlanStep().run(context, CaptionsPlanParams(max_chars=12), StepIO())
    subtitles = (context.output / "subtitles.ass").read_text(encoding="utf-8")
    assert "Intro" in subtitles
    assert "hello" in subtitles


def test_word_events_falls_back_to_sentence_tokens() -> None:
    events = _word_events(
        {
            "sentences": [
                {
                    "text": "one two",
                    "start_sample": 0,
                    "end_sample": 2000,
                }
            ]
        },
        1000,
    )
    assert [item[2] for item in events] == ["one", "two"]


def test_merge_units_merges_short_units() -> None:
    units = [
        {
            "unit_id": "A",
            "start_sec": 0,
            "end_sec": 1,
            "duration_sec": 1,
            "narration": "a",
            "visual": "x",
        },
        {
            "unit_id": "B",
            "start_sec": 1,
            "end_sec": 2,
            "duration_sec": 1,
            "narration": "b",
            "visual": "y",
        },
    ]
    merged = _merge_units(units, min_seconds=2, max_seconds=10, target=1)
    assert len(merged) == 1
    assert merged[0]["duration_sec"] == 2


def test_storyboard_timed_requires_script(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with pytest.raises(IngestError):
        StoryboardTimedStep().run(context, TimedUnitsParams(), StepIO())


def test_motion_callout_skips_without_units(tmp_path: Path) -> None:
    context = _context(tmp_path)
    MotionCalloutStep().run(context, MotionCalloutParams(), StepIO())
    assert context.metadata["motion_callouts"]["count"] == 0


def test_composite_matte_writes_a_plan(tmp_path: Path) -> None:
    context = _context(tmp_path)
    (context.output / "vision").mkdir(parents=True)
    (context.output / "vision" / "segments.json").write_text(
        json.dumps({"masks": [{"mask": "/tmp/mask.png"}]})
    )
    CompositeMatteStep().run(context, CompositeMatteParams(), StepIO())
    payload = json.loads((context.output / "motion" / "matte-plan.json").read_text())
    assert payload["status"] == "review"
    assert context.metadata["matte_plan"]["masks"][0]["mask"] == "/tmp/mask.png"


def test_composite_matte_without_masks_warns(tmp_path: Path) -> None:
    context = _context(tmp_path)
    CompositeMatteStep().run(context, CompositeMatteParams(), StepIO())
    assert any("No subject mask" in item for item in context.warnings)


def test_motion_helpers_wrap_and_track_edges(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    from videoflow.steps import motion_attach as module

    class Draw:
        def textlength(self, text, font):
            return len(text)

    assert len(module._wrap(Draw(), "one two three four five", None, 6)) > 1
    assert module._track_position(
        [{"text": "x", "points": []}], text="x", at=0, width=10, height=10
    ) is None
    assert (
        module._track_position(
            [{"text": "a", "points": [{"time": 0, "x": 10, "y": 20}]}],
            text="b",
            at=0,
            width=0,
            height=0,
        )
        is None
    )

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(module, "find_font", lambda: str(tmp_path / "missing.ttf"))
        target = module.render_callout("hello", tmp_path / "cards" / "one.png")
        assert target.is_file()
    finally:
        monkeypatch.undo()


def test_motion_callout_skips_bad_input_and_render_errors(
    tmp_path: Path, monkeypatch
) -> None:
    from videoflow.steps import motion_attach as module

    context = _context(tmp_path)
    (context.output / "storyboard").mkdir(parents=True)
    (context.output / "storyboard" / "units.json").write_text(
        json.dumps({"units": [1, {"unit_id": "U1", "start_sec": 0, "end_sec": 2, "title": "Card"}]})
    )
    (context.output / "vision").mkdir(parents=True)
    (context.output / "vision" / "ocr.json").write_text(
        json.dumps(
            {
                "frames": [
                    2,
                    {"time_sec": 9, "boxes": [{"text": "late"}]},
                    {"time_sec": 1, "boxes": []},
                ]
            }
        )
    )
    (context.output / "vision" / "tracks.json").write_text(
        json.dumps({"tracks": [{"text": "Card", "points": []}]})
    )
    monkeypatch.setattr(
        module,
        "render_callout",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("no font")),
    )
    module.MotionCalloutStep().run(context, module.MotionCalloutParams(), StepIO())
    assert any("Callout render skipped" in item for item in context.warnings)
    assert context.metadata["motion_callouts"]["count"] == 0


def test_motion_attach_skips_invalid_callouts(tmp_path: Path) -> None:
    from videoflow.domain.state import ProjectState
    from videoflow.steps import motion_attach as module

    context = _context(tmp_path)
    context.media = MediaInfo(
        source_path=str(context.source),
        duration_frames=90,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=48000,
    )
    context.state = ProjectState()
    asset = tmp_path / "card.png"
    asset.write_bytes(b"png")
    (context.output / "motion").mkdir(parents=True)
    (context.output / "motion" / "callouts.json").write_text(
        json.dumps(
            {
                "callouts": [
                    3,
                    {"path": str(tmp_path / "missing.png")},
                    {
                        "callout_id": "C1",
                        "path": str(asset),
                        "start_sec": 1,
                        "duration_sec": 1,
                    },
                ]
            }
        )
    )
    module.MotionAttachStep().run(context, module.MotionAttachParams(), StepIO())
    assert context.metadata["motion_attached"]["count"] == 1
    assert module.MotionAttachStep().cache_outputs(context)


def test_motion_cache_outputs_without_artifacts(tmp_path: Path) -> None:
    from videoflow.steps import motion_attach as module

    context = _context(tmp_path)
    assert module.MotionCalloutStep().cache_outputs(context) == ()
    assert module.MotionAttachStep().cache_outputs(context) == ()
    assert module.CompositeMatteStep().cache_outputs(context) == ()
