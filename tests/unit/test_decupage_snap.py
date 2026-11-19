from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application.decupage.snap import build_plan, report_markdown
from videoflow.core.context import PipelineContext
from videoflow.domain.decupage import Asu, AsuWord, DecupagePlan
from videoflow.domain.errors import TimelineConflict
from videoflow.domain.state import MediaInfo, ProjectState
from videoflow.steps.base import StepIO
from videoflow.steps.decupage_snap import (
    DecupageTimelineParams,
    DecupageTimelineStep,
)


def _media() -> MediaInfo:
    return MediaInfo(
        source_path="/tmp/source.mp4",
        duration_frames=100,
        fps_num=25,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=16_000,
    )


def _word(index: int, text: str, start: int, end: int) -> AsuWord:
    return AsuWord(
        idx=index,
        w=text,
        start_sample=start,
        end_sample=end,
        start_sec=start / 16_000,
        end_sec=end / 16_000,
        p=0.9,
    )


def _asu(identifier: int, start: int, end: int) -> Asu:
    return Asu(
        asu_id=f"ASU_{identifier:04d}",
        start_sample=start,
        end_sample=end,
        start_sec=start / 16_000,
        end_sec=end / 16_000,
        text="uma frase",
        words=[
            _word(0, "uma", start, (start + end) // 2),
            _word(1, "frase", (start + end) // 2, end),
        ],
        avg_word_prob=0.9,
    )


def _profile() -> dict:
    return {
        "sample_rate": 16_000,
        "hop_samples": 160,
        "db": [-10.0] * 100,
    }


def test_snap_plan_quantizes_and_records_joins() -> None:
    plan = build_plan(
        _media(),
        [_asu(1, 0, 1000), _asu(2, 5000, 6000)],
        [{"start_sample": 1000, "end_sample": 5000, "reason": "decupage_remove"}],
        profile=_profile(),
        noise_events=[],
        review_flags=[],
        min_clip_ms=0,
    )
    assert isinstance(plan, DecupagePlan)
    assert plan.active_spans
    assert all(span.start_sample % 640 == 0 for span in plan.active_spans)
    assert plan.joins
    assert plan.metrics["cuts"] == 1
    assert "Decupagem" in report_markdown(plan)


def test_snap_merges_micro_gap_but_not_noise() -> None:
    merged = build_plan(
        _media(),
        [_asu(1, 0, 1000), _asu(2, 1200, 2000)],
        [],
        profile=_profile(),
        noise_events=[],
        review_flags=[],
        min_clip_ms=0,
    )
    assert len(merged.active_spans) == 1
    noisy = build_plan(
        _media(),
        [_asu(1, 0, 1000), _asu(2, 1200, 2000)],
        [],
        profile=_profile(),
        noise_events=[
            {"start_sample": 1000, "end_sample": 1200, "action": "remove"}
        ],
        review_flags=[],
        min_clip_ms=0,
    )
    assert len(noisy.active_spans) == 2


def test_timeline_applies_plan_and_guards_revision(tmp_path: Path) -> None:
    plan = build_plan(
        _media(),
        [_asu(1, 0, 1000), _asu(2, 5000, 6000)],
        [{"start_sample": 1000, "end_sample": 5000, "reason": "decupage_remove"}],
        profile=_profile(),
        noise_events=[],
        review_flags=[],
        min_clip_ms=0,
    )
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out",
        work=tmp_path / "out" / "work",
        exports=tmp_path / "out" / "exports",
        media=_media(),
        state=ProjectState(media_info=_media(), revision=1),
        metadata={"decupage_plan": plan.model_dump(mode="json")},
    )
    DecupageTimelineStep().run(
        context,
        DecupageTimelineParams(expected_revision=1, replace_manual=False),
        StepIO(),
    )
    assert context.state is not None
    assert context.state.video_segments
    assert context.metadata["decupage_timeline"]["video_segments"] == len(
        context.state.video_segments
    )
    assert context.metadata["decupage_quarantine"]
    assert Path(context.artifacts["decupage_quarantine"]).is_file()
    assert (tmp_path / "out" / "timeline_meta.json").is_file()

    context.state = context.state.model_copy(update={"revision": 2})
    with pytest.raises(TimelineConflict):
        DecupageTimelineStep().run(
            context,
            DecupageTimelineParams(expected_revision=1, replace_manual=False),
            StepIO(),
        )
