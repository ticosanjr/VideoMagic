"""Shorts selection fallbacks for analysis, virality, and hook overrides."""

from __future__ import annotations

from pathlib import Path

from tests.unit.test_steps_coverage_extra import (
    make_context,
    make_media,
    sentence,
)
from videoflow.application.shorts import ShortClip
from videoflow.domain.errors import IngestError
from videoflow.steps import shorts_select
from videoflow.steps.base import StepIO

RATE = 48000


def _context(tmp_path: Path, *sentences):
    return make_context(
        tmp_path,
        media_info=make_media(tmp_path, duration_frames=1800),
        transcript=list(sentences),
    )


def test_select_handles_failed_analysis_and_best_effort_threshold(
    tmp_path: Path, monkeypatch
) -> None:
    context = _context(
        tmp_path,
        sentence(0, 0, 40 * RATE, "A complete sentence."),
        sentence(1, 40 * RATE, 80 * RATE, "Another sentence."),
    )
    clip = ShortClip(
        title="One",
        start_sample=0,
        end_sample=40 * RATE,
        sentence_ids=(0,),
        pieces=((0, 40 * RATE),),
        virality_score=12.0,
    )

    monkeypatch.setattr(shorts_select, "cached_scene_changes", lambda *args: [])
    monkeypatch.setattr(
        shorts_select,
        "scene_intervals",
        lambda *args, **kwargs: (_ for _ in ()).throw(IngestError("scene failed")),
    )
    monkeypatch.setattr(
        shorts_select,
        "cached_audio_energy",
        lambda *args: (_ for _ in ()).throw(IngestError("energy failed")),
    )
    monkeypatch.setattr(shorts_select, "select_shorts", lambda *args, **kwargs: [clip])

    shorts_select.ShortsSelectStep().run(
        context,
        shorts_select.ShortsConfig(
            scene_change_boost=True,
            audio_energy_boost=True,
            virality_threshold=99.0,
            reframe_mode="motion_tracking",
            hook_overrides={"0": "Rewritten"},
        ),
        StepIO(),
    )

    assert [item["title"] for item in context.shorts] == ["Rewritten"]
    assert context.shorts[0]["original_title"] == "One"
    assert any("Scene analysis skipped" in item for item in context.warnings)
    assert any("Audio energy analysis skipped" in item for item in context.warnings)
    assert any("virality threshold" in item for item in context.warnings)
    assert any("shorts.reframe" in item for item in context.warnings)
    assert context.metadata["hook_criteria"] == []


def test_select_keeps_clips_above_virality_threshold(tmp_path: Path, monkeypatch) -> None:
    context = _context(
        tmp_path,
        sentence(0, 0, 40 * RATE, "A complete sentence."),
    )
    good = ShortClip(
        title="Good",
        start_sample=0,
        end_sample=40 * RATE,
        sentence_ids=(0,),
        pieces=((0, 40 * RATE),),
        virality_score=80.0,
    )
    monkeypatch.setattr(shorts_select, "select_shorts", lambda *args, **kwargs: [good])

    shorts_select.ShortsSelectStep().run(
        context,
        shorts_select.ShortsConfig(virality_threshold=50.0),
        StepIO(),
    )

    assert [item["title"] for item in context.shorts] == ["Good"]
    assert not any("virality threshold" in item for item in context.warnings)
