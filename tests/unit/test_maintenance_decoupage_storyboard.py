from __future__ import annotations

import json
import os
import time
from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo
from videoflow.engine import maintenance
from videoflow.steps.base import StepIO
from videoflow.steps.decupage import DecoupageCalibrateParams, DecoupageCalibrateStep
from videoflow.steps.storyboard_timed import (
    StoryboardTimedStep,
    TimedUnitsParams,
    _layout,
    _merge_units,
    _word_events,
)


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    output.mkdir(parents=True)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    return PipelineContext(
        source=source,
        output=output,
        work=output / "work",
        exports=output / "exports",
        media=MediaInfo(
            source_path=str(source),
            duration_frames=300,
            fps_num=30,
            fps_den=1,
            width=1280,
            height=720,
            audio_sample_rate=48000,
        ),
    )


def test_prune_output_removes_old_entries(tmp_path: Path) -> None:
    output = tmp_path / "out"
    old = time.time() - 40 * 86400
    steps = output / "work" / "steps"
    for index in range(3):
        directory = steps / f"step-{index}"
        directory.mkdir(parents=True)
        (directory / "state.json").write_text("{}")
        os.utime(directory, (old, old))

    broll = output / "broll-cache" / "old-dir"
    broll.mkdir(parents=True)
    (broll / "image.png").write_bytes(b"png")
    os.utime(broll, (old, old))
    old_file = output / "broll-cache" / "old.bin"
    old_file.write_bytes(b"x")
    os.utime(old_file, (old, old))

    for kind in ("preview/frames", "render/segments"):
        directory = output / kind
        directory.mkdir(parents=True)
        item = directory / "frame.bin"
        item.write_bytes(b"y")
        os.utime(item, (old, old))

    legacy = output / "preview" / "timeline-preview.mp4"
    legacy.write_bytes(b"legacy")
    partial = output / "render" / "x.part.mp4"
    partial.write_bytes(b"partial")
    os.utime(partial, (old, old))

    report = maintenance.prune_output(output, keep_days=1, keep_steps=1, dry_run=True)
    assert report["ok"] is True
    assert {item["kind"] for item in report["removed"]} >= {
        "checkpoint",
        "broll",
        "preview-frame",
        "render-segment",
        "preview-intermediate",
        "partial",
    }
    assert legacy.is_file()

    applied = maintenance.prune_output(
        output, keep_days=1, keep_steps=1, dry_run=False
    )
    assert applied["freed_bytes"] > 0
    assert not legacy.exists()
    assert not partial.exists()


def test_decoupage_calibration_skip_paths(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "videoflow.steps.decupage.allowed_roots", lambda: [tmp_path]
    )
    context = _context(tmp_path)
    DecoupageCalibrateStep().run(context, DecoupageCalibrateParams(), StepIO())
    assert context.metadata["decoupage_profile"]["available"] is False
    assert context.artifacts["decoupage_profile"]
    assert DecoupageCalibrateStep().cache_outputs(context)

    missing = _context(tmp_path / "missing")
    DecoupageCalibrateStep().run(
        missing,
        DecoupageCalibrateParams(baseline_path="reference.xml"),
        StepIO(),
    )
    assert "missing" in missing.metadata["decoupage_profile"]["reason"]
    assert missing.warnings


def test_word_events_skip_malformed_entries() -> None:
    events = _word_events(
        {
            "sentences": [
                1,
                {"words": [1, {"word": "", "start_sample": 0, "end_sample": 10}]},
                {"words": [{"word": "ok", "start_sample": 0, "end_sample": 10}], "text": "skip"},
                {"text": "", "start_sample": 0, "end_sample": 10},
                {"text": "bad", "start_sample": 10, "end_sample": 10},
                {"text": "one two", "start_sample": 0, "end_sample": 2000},
            ]
        },
        1000,
    )
    assert ("ok", 0.0, 0.01) in [(text, start, end) for start, end, text in events]
    assert [text for _start, _end, text in events][-2:] == ["one", "two"]


def test_layout_and_merge_units() -> None:
    assert _layout("close-up") == "presenter_close"
    assert _layout("split screen") == "presenter_split"
    assert _layout("visual b-roll") == "presenter_visual"
    units = [
        {"start_sec": 0, "end_sec": 1, "duration_sec": 1, "narration": "a", "visual": "x"},
        {"start_sec": 1, "end_sec": 2, "duration_sec": 1, "narration": "b", "visual": "x"},
        {"start_sec": 2, "end_sec": 12, "duration_sec": 10, "narration": "c", "visual": "y"},
    ]
    merged = _merge_units(units, min_seconds=2, max_seconds=20, target=1)
    assert len(merged) == 1
    assert merged[0]["narration"] == "a b c"
    assert merged[0]["visual"] == "x"
    assert merged[0]["unit_id"] == "UNIT-0001"


def test_storyboard_timed_handles_sections_without_words(tmp_path: Path) -> None:
    context = _context(tmp_path)
    (context.output / "script").mkdir(parents=True)
    (context.output / "script" / "script.json").write_text(
        json.dumps(
            {
                "sections": [
                    1,
                    {
                        "title": "Intro",
                        "narration": "",
                        "visual": "close-up",
                        "duration_sec": 5,
                    },
                    {
                        "title": "Body",
                        "narration": "one two",
                        "visual": "split",
                    },
                ]
            }
        )
    )
    (context.output / "narration").mkdir(parents=True)
    (context.output / "narration" / "transcript.json").write_text(
        json.dumps({"sample_rate": 1000, "sentences": []})
    )
    StoryboardTimedStep().run(context, TimedUnitsParams(), StepIO())
    units = context.metadata["storyboard_units"]
    assert units[0]["layout"] == "presenter_close"
    assert units[0]["duration_sec"] >= 1
    assert units[1]["layout"] == "presenter_split"
    assert StoryboardTimedStep().cache_outputs(context)
