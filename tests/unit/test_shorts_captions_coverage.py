"""Shorts caption generation branches without the renderer."""

from __future__ import annotations

from pathlib import Path

from tests.unit.test_steps_coverage_extra import (
    make_clip,
    make_context,
    make_media,
    sentence,
)
from videoflow.steps.base import StepIO
from videoflow.steps.shorts_captions import CaptionsParams, CaptionsStep

RATE = 48000


def base_context(tmp_path: Path):
    context = make_context(
        tmp_path,
        media_info=make_media(tmp_path),
        transcript=[sentence(0, 0, 2 * RATE, "Hello world.")],
    )
    return context


def test_captions_disabled_and_no_shorts(tmp_path: Path) -> None:
    context = base_context(tmp_path)
    CaptionsStep().run(context, CaptionsParams(enabled=False), StepIO())
    assert context.short_captions == {}
    assert context.metadata["captions_disabled"] is True

    context.metadata.pop("captions_disabled")
    CaptionsStep().run(context, CaptionsParams(), StepIO())
    assert context.short_captions == {}


def test_captions_skip_clips_without_kept_sentences(tmp_path: Path) -> None:
    context = base_context(tmp_path)
    context.selected_shorts = [make_clip("One", start=0, end=2 * RATE)]
    context.discard_sentence_ids = [0]

    CaptionsStep().run(context, CaptionsParams(), StepIO())

    assert context.short_captions == {}
    assert CaptionsStep().cache_outputs(context) == ()


def test_captions_fall_back_to_sentence_events(tmp_path: Path, monkeypatch) -> None:
    from videoflow.steps import shorts_captions

    context = base_context(tmp_path)
    context.selected_shorts = [make_clip("One", start=0, end=2 * RATE)]
    monkeypatch.setattr(shorts_captions, "caption_lines", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        shorts_captions,
        "sentence_events",
        lambda *args, **kwargs: [(0.0, 1.0, "Fallback caption")],
    )

    CaptionsStep().run(context, CaptionsParams(), StepIO())

    path = Path(context.short_captions["One"])
    assert "Fallback caption" in path.read_text(encoding="utf-8")


def test_captions_write_ass_with_preset_and_short_entry(tmp_path: Path) -> None:
    context = base_context(tmp_path)
    context.selected_shorts = [make_clip("One", start=0, end=2 * RATE)]
    context.shorts = [{"width": 720, "height": 1280}]

    CaptionsStep().run(
        context,
        CaptionsParams(preset="tiktok_bold"),
        StepIO(),
    )

    path = Path(context.short_captions["One"])
    assert path.is_file()
    assert context.shorts[0]["subtitles"] == str(path)
    assert "caption" not in context.metadata
    assert CaptionsStep().cache_outputs(context) == (path,)
