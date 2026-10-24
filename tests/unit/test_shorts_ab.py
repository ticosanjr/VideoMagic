"""Hook and duration A/B variant generation."""

from __future__ import annotations

from pathlib import Path

from videoflow.application.shorts import ShortClip
from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo
from videoflow.steps.base import StepIO
from videoflow.steps.shorts_ab import AbParams, ShortsAbStep


def build(tmp_path: Path) -> PipelineContext:
    media = MediaInfo(
        source_path=str(tmp_path / "source.mp4"),
        duration_frames=100,
        fps_num=25,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )
    clip = ShortClip(
        title="One",
        start_sample=0,
        end_sample=48000,
        sentence_ids=(0, 1),
        pieces=((0, 48000),),
        hook_text="Hook",
        hook_sentence_id=1,
        hook_start_sample=24000,
        hook_end_sample=36000,
    )
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        media=media,
        selected_shorts=[clip],
    )


def test_generates_hook_and_duration_variants(tmp_path: Path) -> None:
    context = build(tmp_path)

    ShortsAbStep().run(
        context,
        AbParams(hooks=["original", "repeat"], duration_factors=[1.0, 0.8], max_variants=4),
        StepIO(stage="ab"),
    )

    assert len(context.selected_shorts) == 4
    titles = [clip.title for clip in context.selected_shorts]
    assert "One · repeat-100" in titles
    assert "One · original-80" in titles
    repeat = next(clip for clip in context.selected_shorts if clip.title.endswith("repeat-100"))
    assert repeat.pieces[0] == (24000, 36000)
    short = next(clip for clip in context.selected_shorts if clip.title.endswith("original-80"))
    total = sum(end - start for start, end in short.pieces)
    assert total == 38400
    assert len(context.metadata["ab_variants"]) == 4


def test_no_shorts_is_a_noop(tmp_path: Path) -> None:
    context = build(tmp_path)
    context.selected_shorts = []
    ShortsAbStep().run(context, AbParams(), StepIO(stage="ab"))
    assert context.selected_shorts == []
