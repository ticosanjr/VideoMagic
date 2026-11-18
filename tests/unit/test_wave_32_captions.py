from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application.captions import CaptionLine, build_ass_lines, caption_lines
from videoflow.application.word_cuts import plan_word_cuts
from videoflow.core.context import PipelineContext
from videoflow.domain.config import CaptionStyle
from videoflow.domain.errors import RecipeError
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    Sentence,
    VideoSegment,
    WordTiming,
)
from videoflow.steps.base import StepIO
from videoflow.steps.qa_caption import CaptionEffectParams, CaptionEffectStep


def _state(tmp_path: Path) -> ProjectState:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=90,
        fps_num=30,
        fps_den=1,
        width=1080,
        height=1920,
        audio_sample_rate=48000,
    )
    return ProjectState(
        media_info=media,
        sources={"primary": media},
        primary_source_id="primary",
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_id="primary",
                source_in_frame=0,
                source_out_frame=90,
                timeline_in_frame=0,
                timeline_out_frame=90,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_id="primary",
                source_in_sample=0,
                source_out_sample=144000,
                timeline_in_sample=0,
                timeline_out_sample=144000,
            )
        ],
    )


def test_effect_fallback_and_stable_blocks() -> None:
    sentence = Sentence(
        id=0, start_sample=0, end_sample=48000, text="one two three four five six seven eight"
    )
    lines = caption_lines(
        [sentence],
        [(0, 48000)],
        sample_rate=48000,
        effect="karaoke_sweep",
    )
    assert lines
    assert lines[0].effect_fallback is True
    assert all(line.words for line in lines)
    assert all(4 <= len(line.words) <= 6 for line in lines if len(lines) > 1)
    ass = build_ass_lines(lines, style=CaptionStyle(effect="karaoke_sweep"))
    assert "\\kf" in ass and "\\\\kf" not in ass


def test_low_confidence_words_are_not_cut_anchors() -> None:
    sentence = Sentence(
        id=0,
        start_sample=0,
        end_sample=8000,
        text="hello hello",
        words=[
            WordTiming(
                word="hello", start_sample=0, end_sample=1000, probability=0.1, low_confidence=True
            ),
            WordTiming(
                word="hello",
                start_sample=1200,
                end_sample=2000,
                probability=0.1,
                low_confidence=True,
            ),
        ],
    )
    plan = plan_word_cuts([sentence], set(), sample_rate=48000)
    assert plan.cuts == []


def test_caption_effect_step(tmp_path: Path) -> None:
    state = _state(tmp_path)
    context = PipelineContext(
        source=Path(state.media_info.source_path),
        output=tmp_path,
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        media=state.media_info,
        state=state,
    )
    ass = tmp_path / "captions" / "captions.ass"
    ass.parent.mkdir(parents=True)
    ass.write_text(
        build_ass_lines(
            [CaptionLine(0, 1, "ok", ((0.0, 1.0, "ok"),), 0)],
            style=CaptionStyle(effect="karaoke_sweep"),
            width=1080,
            height=1920,
        ),
        encoding="utf-8",
    )
    context.artifacts["captions_ass"] = str(ass)
    CaptionEffectStep().run(context, CaptionEffectParams(strict=False), StepIO())
    assert context.metadata["caption_effect"]["ok"] is True
    ass.write_text("Dialogue: broken\n", encoding="utf-8")
    with_tmp = tmp_path / "captions" / "broken.ass"
    with_tmp.write_text(
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,plain\n",
        encoding="utf-8",
    )
    with pytest.raises(RecipeError):
        CaptionEffectStep().run(
            context,
            CaptionEffectParams(
                path=str(with_tmp),
                effect="karaoke_sweep",
                max_chars=1,
                strict=True,
            ),
            StepIO(),
        )
