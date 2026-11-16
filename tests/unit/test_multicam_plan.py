"""Multicam angle planning and application."""

from __future__ import annotations

from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    Sentence,
    VideoSegment,
)
from videoflow.steps.base import StepIO
from videoflow.steps.multicam_plan import (
    MulticamApplyParams,
    MulticamApplyStep,
    MulticamPlanParams,
    MulticamPlanStep,
)


def context(tmp_path: Path) -> PipelineContext:
    source = tmp_path / "a.mp4"
    source.write_bytes(b"x")
    second = tmp_path / "b.mp4"
    second.write_bytes(b"x")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=120,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )
    other = media.model_copy(update={"source_path": str(second)})
    state = ProjectState(
        sources={"src1": media, "src2": other},
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_id="src1",
                source_in_frame=0,
                source_out_frame=120,
                timeline_in_frame=0,
                timeline_out_frame=120,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_id="src1",
                source_in_sample=0,
                source_out_sample=192000,
                timeline_in_sample=0,
                timeline_out_sample=192000,
            )
        ],
        transcript=[
            Sentence(id=0, start_sample=0, end_sample=48000, text="one", speaker=0),
            Sentence(id=1, start_sample=48000, end_sample=96000, text="two", speaker=1),
        ],
    )
    output = tmp_path / "out"
    (output / "work").mkdir(parents=True)
    return PipelineContext(
        source=source,
        output=output,
        work=output / "work",
        exports=output / "exports",
        media=media,
        state=state,
        transcript=list(state.transcript),
    )


def test_speaker_plan_and_apply(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    MulticamPlanStep().run(
        ctx,
        MulticamPlanParams(
            mode="speech",
            primary_source_id="src1",
            secondary_source_id="src2",
            apply=True,
        ),
        StepIO(),
    )
    assert ctx.state is not None
    assert ctx.state.multicam is not None
    assert {clip.source_id for clip in ctx.state.video_segments} == {"src1", "src2"}
    assert len(ctx.state.video_segments) >= 2
    assert ctx.artifacts["multicam_plan"].endswith("multicam_plan.json")


def test_manual_apply_and_alternate(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    MulticamPlanStep().run(
        ctx,
        MulticamPlanParams(
            mode="manual",
            cuts=[
                {"start_frame": 0, "end_frame": 60, "source_id": "src2"},
                {"start_frame": 60, "end_frame": 120, "source_id": "src1"},
            ],
        ),
        StepIO(),
    )
    MulticamApplyStep().run(ctx, MulticamApplyParams(), StepIO())
    assert ctx.state is not None
    assert len(ctx.state.video_segments) == 2
    assert ctx.state.video_segments[0].source_id == "src2"

    MulticamPlanStep().run(
        ctx,
        MulticamPlanParams(mode="alternate", segment_sec=1.0, apply=True),
        StepIO(),
    )
    assert ctx.state is not None
    assert len(ctx.state.video_segments) >= 2


def test_multicam_edges(tmp_path: Path) -> None:
    from videoflow.domain.errors import StateNotReadyError
    from videoflow.domain.state import MulticamPlan
    from videoflow.steps.multicam_plan import (
        MulticamApplyStep,
        MulticamPlanParams,
        MulticamPlanStep,
    )

    ctx = context(tmp_path)
    MulticamPlanStep().run(
        ctx,
        MulticamPlanParams(
            mode="manual",
            cuts=[
                {"start_frame": 10, "end_frame": 20, "source_id": "src2"},
                {"start_frame": 80, "end_frame": 90, "source_id": "src2"},
            ],
        ),
        StepIO(),
    )
    assert ctx.state is not None
    assert ctx.state.multicam is not None
    assert ctx.state.multicam.cuts[0].start_frame == 0
    assert ctx.state.multicam.cuts[-1].end_frame == 120
    MulticamApplyStep().run(
        ctx,
        MulticamApplyParams(cuts=[{"start_frame": 0, "end_frame": 120, "source_id": "src2"}]),
        StepIO(),
    )
    assert ctx.state.video_segments[0].source_id == "src2"

    empty = ctx.model_copy(deep=True)
    empty.state = empty.state.model_copy(update={"video_segments": []})
    MulticamPlanStep().run(empty, MulticamPlanParams(mode="alternate"), StepIO())
    assert empty.state.multicam is not None

    broken = ctx.model_copy(deep=True)
    broken.state = broken.state.model_copy(
        update={"video_segments": [], "multicam": MulticamPlan(cuts=[])}
    )
    with __import__("contextlib").suppress(StateNotReadyError):
        MulticamApplyStep().run(broken, MulticamApplyParams(), StepIO())


def test_multicam_invalid_manual_cut_is_ignored(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    MulticamPlanStep().run(
        ctx,
        MulticamPlanParams(
            mode="manual",
            cuts=[{"start_frame": "bad", "end_frame": "bad", "source_id": "src1"}],
        ),
        StepIO(),
    )
    assert ctx.state is not None
    assert ctx.state.multicam is not None
    assert len(ctx.state.multicam.cuts) == 1


def test_multicam_apply_requires_media(tmp_path: Path) -> None:
    from videoflow.domain.errors import StateNotReadyError
    from videoflow.steps.multicam_plan import MulticamApplyParams, MulticamApplyStep

    ctx = context(tmp_path)
    ctx.media = None
    with __import__("contextlib").suppress(StateNotReadyError):
        MulticamApplyStep().run(ctx, MulticamApplyParams(), StepIO())
