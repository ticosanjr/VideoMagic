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
from videoflow.steps.base import StepIO
from videoflow.steps.llm_timeline import LlmTimelineParams, LlmTimelineStep


def _state() -> ProjectState:
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
        video_segments=[
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
        ],
        audio_segments=[
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
        ],
    )


class FakeLlm:
    def __init__(self, actions: list[dict[str, Any]]) -> None:
        self.actions = actions
        self.prompt = ""

    def complete_json(self, prompt: str, schema_name: str) -> dict[str, Any]:
        self.prompt = prompt
        return {"edits": self.actions, "reasoning": "trim and style"}


def test_apply_actions_crops_styles_and_zooms() -> None:
    working, applied, rejected = apply_actions(
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
    assert len(applied) == 3
    assert len(rejected) == 2
    first = next(clip for clip in working.video_segments if clip.clip_id == "c1")
    assert first.timeline_in_frame == 15
    assert first.transform.type == "slow_zoom_in"
    assert first.transform.keyframes[0].scale == 1.0
    assert first.transform.keyframes[-1].scale == 1.3
    second = next(clip for clip in working.video_segments if clip.clip_id == "c2")
    assert second.transition_out is not None
    assert second.transition_out.type == "fade_to_black"
    audio = next(clip for clip in working.audio_segments if clip.clip_id == "c2")
    assert audio.fade_in_samples == 9600


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
    assert context.state.video_segments[0].transform.scale == 1.2
    assert "zoom the opening" in client.prompt


def test_propose_actions_returns_empty_for_bad_shape(tmp_path: Path) -> None:
    client = FakeLlm([])
    client.complete_json = lambda prompt, schema: {"nope": True}  # type: ignore[method-assign]
    actions, reasoning = propose_actions(client, "x", _state())
    assert actions == []
    assert reasoning
