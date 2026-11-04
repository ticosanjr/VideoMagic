from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.application.llm_timeline import apply_actions, propose_actions
from videoflow.core.context import PipelineContext
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    VideoSegment,
)
from videoflow.domain.timeline import is_packed
from videoflow.steps.base import StepIO
from videoflow.steps.llm_timeline import LlmTimelineParams, LlmTimelineStep


def _state(*, three_clips: bool = False) -> ProjectState:
    video = [
        VideoSegment(
            clip_id="c1",
            source_in_frame=0,
            source_out_frame=90,
            timeline_in_frame=0,
            timeline_out_frame=90,
        ),
        VideoSegment(
            clip_id="c2",
            source_in_frame=90,
            source_out_frame=180,
            timeline_in_frame=90,
            timeline_out_frame=180,
        ),
    ]
    audio = [
        AudioSegment(
            clip_id="c1",
            source_in_sample=0,
            source_out_sample=144000,
            timeline_in_sample=0,
            timeline_out_sample=144000,
        ),
        AudioSegment(
            clip_id="c2",
            source_in_sample=144000,
            source_out_sample=288000,
            timeline_in_sample=144000,
            timeline_out_sample=288000,
        ),
    ]
    if three_clips:
        video.append(
            VideoSegment(
                clip_id="c3",
                source_in_frame=180,
                source_out_frame=260,
                timeline_in_frame=180,
                timeline_out_frame=260,
            )
        )
        audio.append(
            AudioSegment(
                clip_id="c3",
                source_in_sample=288000,
                source_out_sample=416000,
                timeline_in_sample=288000,
                timeline_out_sample=416000,
            )
        )
    return ProjectState(
        media_info=MediaInfo(
            source_path="/tmp/source.mp4",
            duration_frames=600,
            fps_num=30,
            fps_den=1,
            width=640,
            height=360,
            audio_sample_rate=48000,
        ),
        video_segments=video,
        audio_segments=audio,
    )


class FakeLlm:
    def __init__(self, actions: list[dict[str, Any]]) -> None:
        self.actions = actions
        self.prompt = ""

    def complete_json(self, prompt: str, schema_name: str) -> dict[str, Any]:
        self.prompt = prompt
        return {"edits": self.actions, "reasoning": "trim and style"}


def _packed(state: ProjectState) -> bool:
    return is_packed(
        [(clip.timeline_in_frame, clip.timeline_out_frame) for clip in state.video_segments]
    ) and is_packed(
        [
            (clip.timeline_in_sample, clip.timeline_out_sample)
            for clip in state.audio_segments
        ]
    )


def test_apply_actions_crops_styles_and_zooms() -> None:
    result = apply_actions(
        _state(),
        [
            {"clip_id": "c1", "action": "crop_in", "start_sec": 0.5},
            {
                "clip_id": "c2",
                "action": "style",
                "transition_type": "fade_to_black",
                "transition_duration_frames": 9,
                "fade_in_sec": 0.2,
            },
            {
                "clip_id": "c1",
                "action": "zoom",
                "zoom_type": "slow_zoom_in",
                "start_scale": 1.0,
                "end_scale": 1.3,
            },
            {"clip_id": "missing", "action": "delete"},
            {"clip_id": "c1", "action": "unknown"},
        ],
    )
    working = result.state
    assert len(result.applied) == 3
    assert len(result.rejected) == 2
    assert result.normalized is True
    assert result.gaps_closed == 1
    assert result.closed_frames == 15
    assert result.closed_seconds == 0.5
    assert _packed(working)
    first = next(clip for clip in working.video_segments if clip.clip_id == "c1")
    assert first.timeline_in_frame == 0
    assert first.timeline_out_frame == 75
    assert first.transform.type == "slow_zoom_in"
    assert first.transform.keyframes[0].scale == 1.0
    assert first.transform.keyframes[-1].scale == 1.3
    second = next(clip for clip in working.video_segments if clip.clip_id == "c2")
    assert second.timeline_in_frame == 75
    assert second.transition_out is not None
    assert second.transition_out.type == "fade_to_black"
    audio = next(clip for clip in working.audio_segments if clip.clip_id == "c2")
    assert audio.fade_in_samples == 9600


def test_apply_actions_closes_gaps_from_delete_and_both_trim_ends() -> None:
    result = apply_actions(
        _state(three_clips=True),
        [
            {"clip_id": "c1", "action": "trim", "start_sec": 0.5, "end_sec": 3.0},
            {"clip_id": "c2", "action": "delete"},
            {"clip_id": "c3", "action": "trim", "end_sec": 8.0},
        ],
    )
    working = result.state
    assert result.normalized is True
    # The tail trim shortens the timeline instead of leaving a trailing gap.
    assert result.gaps_closed == 2
    assert result.closed_frames == 105
    assert result.closed_seconds == 3.5
    assert _packed(working)
    assert [clip.clip_id for clip in working.video_segments] == ["c1", "c3"]
    first = working.video_segments[0]
    last = working.video_segments[1]
    assert (first.timeline_in_frame, first.timeline_out_frame) == (0, 75)
    assert (last.timeline_in_frame, last.timeline_out_frame) == (75, 135)


def test_apply_actions_keeps_a_packed_timeline_untouched() -> None:
    result = apply_actions(
        _state(),
        [{"clip_id": "c1", "action": "zoom", "scale": 1.2}],
    )
    assert result.normalized is False
    assert result.gaps_closed == 0
    assert result.closed_frames == 0
    assert result.closed_seconds == 0.0
    assert result.state.video_segments[0].transform.scale == 1.2


def test_apply_actions_rejects_a_trim_outside_the_clip() -> None:
    state = _state()
    result = apply_actions(
        state,
        [{"clip_id": "c1", "action": "trim", "start_sec": 5.0, "end_sec": 6.0}],
    )
    assert result.applied == []
    assert len(result.rejected) == 1
    assert "outside clip" in result.rejected[0]["error"]
    assert result.state is state
    assert result.normalized is False


def test_apply_actions_rejects_an_edit_that_removes_every_clip() -> None:
    state = _state()
    result = apply_actions(
        state,
        [
            {"clip_id": "c1", "action": "delete"},
            {"clip_id": "c2", "action": "delete"},
        ],
    )
    assert result.applied == []
    assert result.state is state
    assert any("remove every clip" in item["error"] for item in result.rejected)


def test_step_reports_applied_and_rejected_actions(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    work = output / "work"
    exports = output / "exports"
    work.mkdir()
    exports.mkdir()
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=work,
        exports=exports,
    )
    context.state = _state()
    context.source.write_bytes(b"x")
    client = FakeLlm([{"clip_id": "c1", "action": "zoom", "scale": 1.2}])
    step = LlmTimelineStep()
    step.run(
        context,
        LlmTimelineParams(provider_id="deepseek", prompt="zoom the opening"),
        StepIO(llm_client=client),
    )
    report = context.metadata["llm_timeline_report"]
    assert report["applied_count"] == 1
    assert report["normalized"] is False
    assert context.state.video_segments[0].transform.scale == 1.2
    assert "zoom the opening" in client.prompt


def test_step_warns_when_it_closes_gaps(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    work = output / "work"
    exports = output / "exports"
    work.mkdir()
    exports.mkdir()
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=work,
        exports=exports,
    )
    context.state = _state()
    context.source.write_bytes(b"x")
    client = FakeLlm(
        [
            {"clip_id": "c1", "action": "crop_in", "start_sec": 0.5},
            {"clip_id": "c2", "action": "delete"},
        ]
    )
    step = LlmTimelineStep()
    step.run(
        context,
        LlmTimelineParams(provider_id="deepseek", prompt="tighten"),
        StepIO(llm_client=client),
    )
    report = context.metadata["llm_timeline_report"]
    assert report["normalized"] is True
    assert report["gaps_closed"] == 1
    assert any("closed 1 gap" in warning for warning in context.warnings)


def test_propose_actions_returns_empty_for_bad_shape(tmp_path: Path) -> None:
    client = FakeLlm([])
    client.complete_json = lambda prompt, schema: {"nope": True}  # type: ignore[method-assign]
    actions, reasoning = propose_actions(client, "x", _state())
    assert actions == []
    assert reasoning
