"""Property tests for recipe and timeline boundaries."""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from videoflow.application.timeline_edit import TimelineEdit, apply_timeline_edit
from videoflow.core.recipe import parse_recipe
from videoflow.domain.errors import VideoFlowError
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment


def _state() -> ProjectState:
    return ProjectState(
        media_info=MediaInfo(
            source_path="/tmp/source.mp4",
            duration_frames=300,
            fps_num=30,
            fps_den=1,
            width=320,
            height=240,
            audio_sample_rate=48000,
        ),
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_in_frame=0,
                source_out_frame=90,
                timeline_in_frame=0,
                timeline_out_frame=90,
            ),
            VideoSegment(
                clip_id="v2",
                source_in_frame=90,
                source_out_frame=180,
                timeline_in_frame=90,
                timeline_out_frame=180,
            ),
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_in_sample=0,
                source_out_sample=144000,
                timeline_in_sample=0,
                timeline_out_sample=144000,
            ),
            AudioSegment(
                clip_id="v2",
                source_in_sample=144000,
                source_out_sample=288000,
                timeline_in_sample=144000,
                timeline_out_sample=288000,
            ),
        ],
    )


@given(st.dictionaries(st.text(max_size=12), st.integers(), max_size=6))
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_recipe_parser_rejects_arbitrary_payloads_cleanly(payload: dict) -> None:
    try:
        recipe = parse_recipe(payload)
    except (ValidationError, ValueError, VideoFlowError):
        return
    assert recipe.steps


@given(
    action=st.sampled_from(["trim", "move", "split", "delete", "ripple", "duplicate"]),
    start=st.floats(min_value=0.0, max_value=6.0, allow_nan=False, allow_infinity=False),
    end=st.floats(min_value=0.0, max_value=6.0, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=-6.0, max_value=6.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=80, deadline=None)
def test_timeline_edits_never_produce_invalid_ranges(
    action: str, start: float, end: float, delta: float
) -> None:
    state = _state()
    try:
        result = apply_timeline_edit(
            state,
            TimelineEdit(
                clip_id="v1",
                action=action,  # type: ignore[arg-type]
                start_sec=start,
                end_sec=end,
                delta_sec=delta,
                split_sec=start,
            ),
        )
    except (ValueError, KeyError, IndexError, VideoFlowError):
        return
    for clip in result.video_segments:
        assert clip.timeline_out_frame > clip.timeline_in_frame
        assert clip.source_out_frame > clip.source_in_frame
