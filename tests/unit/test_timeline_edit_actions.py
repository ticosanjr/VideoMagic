"""Timeline edit actions beyond the basic split/ripple/delete cases."""

from __future__ import annotations

import pytest

from videoflow.application import timeline_edit
from videoflow.application.timeline_edit import (
    TimelineEdit,
    apply_timeline_edit,
    timeline_duration_sec,
)
from videoflow.domain.errors import InvalidTimeError
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    Transition,
    VideoSegment,
)


def media() -> MediaInfo:
    return MediaInfo(
        source_path="/tmp/source.mp4",
        duration_frames=100,
        fps_num=25,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )


def state_with_three_clips(*, audio: bool = True) -> ProjectState:
    state = ProjectState(
        media_info=media(),
        video_segments=[
            VideoSegment(
                clip_id=f"v{index}",
                source_in_frame=(index - 1) * 25,
                source_out_frame=index * 25,
                timeline_in_frame=(index - 1) * 25,
                timeline_out_frame=index * 25,
            )
            for index in (1, 2, 3)
        ],
    )
    if audio:
        state.audio_segments = [
            AudioSegment(
                clip_id=f"v{index}",
                source_in_sample=(index - 1) * 48000,
                source_out_sample=index * 48000,
                timeline_in_sample=(index - 1) * 48000,
                timeline_out_sample=index * 48000,
            )
            for index in (1, 2, 3)
        ]
    return state


def test_trim_resizes_video_and_audio() -> None:
    state = state_with_three_clips()

    apply_timeline_edit(
        state,
        TimelineEdit(clip_id="v1", action="trim", start_sec=0.2, end_sec=0.6),
    )

    video, audio = state.video_segments[0], state.audio_segments[0]
    assert (video.timeline_in_frame, video.timeline_out_frame) == (5, 15)
    assert (video.source_in_frame, video.source_out_frame) == (5, 15)
    assert (audio.timeline_in_sample, audio.timeline_out_sample) == (9600, 28800)
    assert (audio.source_in_sample, audio.source_out_sample) == (9600, 28800)


def test_trim_requires_a_valid_range() -> None:
    state = state_with_three_clips()

    with pytest.raises(InvalidTimeError, match="requires start and end"):
        apply_timeline_edit(state, TimelineEdit(clip_id="v1", action="trim"))

    with pytest.raises(InvalidTimeError, match="after start"):
        apply_timeline_edit(
            state,
            TimelineEdit(clip_id="v1", action="trim", start_sec=0.6, end_sec=0.2),
        )

    with pytest.raises(InvalidTimeError, match="exceeds source media"):
        apply_timeline_edit(
            state,
            TimelineEdit(clip_id="v1", action="trim", start_sec=0.0, end_sec=5.0),
        )


def test_ripple_trim_shifts_following_clips() -> None:
    state = state_with_three_clips()

    apply_timeline_edit(
        state,
        TimelineEdit(clip_id="v1", action="ripple_trim", start_sec=0.0, end_sec=0.6),
    )

    assert [clip.timeline_in_frame for clip in state.video_segments] == [0, 15, 40]
    assert [clip.timeline_out_sample for clip in state.audio_segments] == [
        28800,
        76800,
        124800,
    ]


def test_ripple_trim_requires_start_and_end() -> None:
    with pytest.raises(InvalidTimeError, match="Ripple trim requires"):
        apply_timeline_edit(
            state_with_three_clips(), TimelineEdit(clip_id="v1", action="ripple_trim")
        )


def test_split_requires_an_interior_point() -> None:
    state = state_with_three_clips()

    with pytest.raises(InvalidTimeError, match="Split requires split_sec"):
        apply_timeline_edit(state, TimelineEdit(clip_id="v1", action="split"))

    with pytest.raises(InvalidTimeError, match="inside the clip"):
        apply_timeline_edit(
            state, TimelineEdit(clip_id="v1", action="split", split_sec=0.0)
        )


def test_split_clears_the_outgoing_transition() -> None:
    state = state_with_three_clips()
    state.video_segments[0].transition_out = Transition()

    apply_timeline_edit(
        state, TimelineEdit(clip_id="v1", action="split", split_sec=0.5)
    )

    assert state.video_segments[0].transition_out is None
    assert state.video_segments[1].clip_id != "v1"


def test_split_without_audio_leaves_audio_untouched() -> None:
    state = state_with_three_clips(audio=False)

    apply_timeline_edit(
        state, TimelineEdit(clip_id="v1", action="split", split_sec=0.5)
    )

    assert len(state.video_segments) == 4
    assert state.audio_segments == []


def test_slip_moves_source_within_the_media() -> None:
    state = state_with_three_clips()

    apply_timeline_edit(
        state, TimelineEdit(clip_id="v1", action="slip", delta_sec=0.2)
    )

    video, audio = state.video_segments[0], state.audio_segments[0]
    assert (video.source_in_frame, video.source_out_frame) == (5, 30)
    assert (audio.source_in_sample, audio.source_out_sample) == (9600, 57600)


def test_slip_rejects_out_of_bounds_and_length_changes() -> None:
    state = state_with_three_clips()

    with pytest.raises(InvalidTimeError, match="exceeds source media"):
        apply_timeline_edit(
            state, TimelineEdit(clip_id="v1", action="slip", delta_sec=4.0)
        )

    state = state_with_three_clips()
    state.video_segments[0].source_in_frame = 10
    state.video_segments[0].source_out_frame = 35
    state.audio_segments[0].source_in_sample = 10
    state.audio_segments[0].source_out_sample = 48010
    with pytest.raises(InvalidTimeError, match="exceeds source audio"):
        apply_timeline_edit(
            state, TimelineEdit(clip_id="v1", action="slip", delta_sec=-0.2)
        )


def test_slide_moves_the_clip_and_its_neighbors() -> None:
    state = state_with_three_clips()

    apply_timeline_edit(
        state, TimelineEdit(clip_id="v2", action="slide", delta_sec=0.2)
    )

    assert [clip.timeline_in_frame for clip in state.video_segments] == [0, 30, 55]
    assert [clip.source_out_frame for clip in state.video_segments] == [30, 50, 75]
    assert state.audio_segments[1].timeline_in_sample == 57600


def test_slide_is_a_noop_without_a_delta() -> None:
    state = state_with_three_clips()
    before = state.model_dump()

    apply_timeline_edit(state, TimelineEdit(clip_id="v2", action="slide"))

    assert state.model_dump() == before


def test_slide_requires_neighbors_and_rolls_back() -> None:
    state = state_with_three_clips()

    with pytest.raises(InvalidTimeError, match="contiguous clip"):
        apply_timeline_edit(
            state, TimelineEdit(clip_id="v1", action="slide", delta_sec=0.2)
        )

    state = state_with_three_clips()
    before = state.model_dump()
    with pytest.raises(InvalidTimeError, match="exceeds the neighboring clips"):
        apply_timeline_edit(
            state, TimelineEdit(clip_id="v2", action="slide", delta_sec=2.0)
        )
    assert state.model_dump() == before


def test_duplicate_inserts_a_copy_and_shifts_following_clips() -> None:
    state = state_with_three_clips()
    state.video_segments[0].transition_out = Transition()

    apply_timeline_edit(state, TimelineEdit(clip_id="v1", action="duplicate"))

    assert [clip.timeline_in_frame for clip in state.video_segments] == [0, 25, 50, 75]
    copy = state.video_segments[1]
    assert copy.clip_id != "v1"
    assert copy.timeline_out_frame == 50
    assert copy.transition_out is None
    assert [clip.timeline_in_sample for clip in state.audio_segments] == [
        0,
        48000,
        96000,
        144000,
    ]
    assert state.audio_segments[1].fade_in_samples == 0


def test_move_rejects_negative_positions() -> None:
    state = state_with_three_clips()

    with pytest.raises(InvalidTimeError, match="before zero"):
        apply_timeline_edit(
            state, TimelineEdit(clip_id="v1", action="move", delta_sec=-1.0)
        )


def test_unknown_clips_and_missing_media_are_actionable() -> None:
    with pytest.raises(InvalidTimeError, match="requires media info"):
        apply_timeline_edit(ProjectState(), TimelineEdit(clip_id="v1", action="delete"))

    for action in ("delete", "ripple", "move", "duplicate"):
        with pytest.raises(InvalidTimeError, match="Unknown clip"):
            apply_timeline_edit(
                state_with_three_clips(), TimelineEdit(clip_id="missing", action=action)
            )


def test_timeline_duration_uses_the_last_out_frame() -> None:
    assert timeline_duration_sec(state_with_three_clips()) == 3.0
    assert timeline_duration_sec(ProjectState(media_info=media())) == 0.0


def test_clip_id_allocation_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeUuid:
        hex = "abcdef123456"

    monkeypatch.setattr(timeline_edit, "uuid4", lambda: FakeUuid())

    with pytest.raises(InvalidTimeError, match="Could not allocate"):
        timeline_edit._new_clip_id({"v1-abcdef"}, "v1")


def test_deactivate_and_activate_round_trip_keeps_packed_timeline() -> None:
    state = state_with_three_clips()

    apply_timeline_edit(
        state, TimelineEdit(clip_id="v2", action="deactivate")
    )

    assert [clip.clip_id for clip in state.video_segments] == ["v1", "v3"]
    assert [clip.clip_id for clip in state.audio_segments] == ["v1", "v3"]
    assert [(clip.timeline_in_frame, clip.timeline_out_frame) for clip in state.video_segments] == [
        (0, 25),
        (25, 50),
    ]
    assert [item.clip_id for item in state.inactive_segments] == ["v2"]
    assert state.inactive_segments[0].reason == "manual"

    apply_timeline_edit(state, TimelineEdit(clip_id="v2", action="activate"))

    assert [clip.clip_id for clip in state.video_segments] == ["v1", "v2", "v3"]
    assert [clip.clip_id for clip in state.audio_segments] == ["v1", "v2", "v3"]
    assert state.inactive_segments == []
    assert [(clip.timeline_in_frame, clip.timeline_out_frame) for clip in state.video_segments] == [
        (0, 25),
        (25, 50),
        (50, 75),
    ]


def test_activate_unknown_clip_is_rejected() -> None:
    state = state_with_three_clips()
    with pytest.raises(InvalidTimeError, match="Unknown inactive"):
        apply_timeline_edit(state, TimelineEdit(clip_id="missing", action="activate"))


def test_recut_grows_the_inactive_range_into_both_neighbors() -> None:
    state = state_with_three_clips()
    apply_timeline_edit(state, TimelineEdit(clip_id="v2", action="deactivate"))
    item = state.inactive_segments[0]
    item.reason = "silence"

    apply_timeline_edit(
        state,
        TimelineEdit(clip_id="v2", action="recut", start_sec=0.6, end_sec=2.4),
    )

    assert (item.video.source_in_frame, item.video.source_out_frame) == (15, 60)
    assert (item.audio.source_in_sample, item.audio.source_out_sample) == (
        28800,
        115200,
    )
    assert item.reason == "silence"
    assert [
        (clip.clip_id, clip.source_in_frame, clip.source_out_frame)
        for clip in state.video_segments
    ] == [("v1", 0, 15), ("v3", 60, 75)]
    assert [
        (clip.timeline_in_frame, clip.timeline_out_frame)
        for clip in state.video_segments
    ] == [(0, 15), (15, 30)]
    assert [
        (clip.clip_id, clip.source_in_sample, clip.source_out_sample)
        for clip in state.audio_segments
    ] == [("v1", 0, 28800), ("v3", 115200, 144000)]
    assert [
        (clip.timeline_in_sample, clip.timeline_out_sample)
        for clip in state.audio_segments
    ] == [(0, 28800), (28800, 57600)]


def test_recut_shrinks_the_inactive_range_and_expands_neighbors() -> None:
    state = state_with_three_clips()
    apply_timeline_edit(state, TimelineEdit(clip_id="v2", action="deactivate"))

    apply_timeline_edit(
        state,
        TimelineEdit(clip_id="v2", action="recut", start_sec=1.2, end_sec=1.8),
    )

    item = state.inactive_segments[0]
    assert (item.video.source_in_frame, item.video.source_out_frame) == (30, 45)
    assert (item.audio.source_in_sample, item.audio.source_out_sample) == (
        57600,
        86400,
    )
    assert [
        (clip.clip_id, clip.source_in_frame, clip.source_out_frame)
        for clip in state.video_segments
    ] == [("v1", 0, 30), ("v3", 45, 75)]
    assert [
        (clip.timeline_in_frame, clip.timeline_out_frame)
        for clip in state.video_segments
    ] == [(0, 30), (30, 60)]
    assert [
        (clip.clip_id, clip.source_in_sample, clip.source_out_sample)
        for clip in state.audio_segments
    ] == [("v1", 0, 57600), ("v3", 86400, 144000)]


def test_recut_keeps_edges_without_an_adjacent_active_clip() -> None:
    leading = state_with_three_clips()
    apply_timeline_edit(leading, TimelineEdit(clip_id="v1", action="deactivate"))
    with pytest.raises(InvalidTimeError, match="no preceding clip"):
        apply_timeline_edit(
            leading,
            TimelineEdit(clip_id="v1", action="recut", start_sec=0.2, end_sec=1.0),
        )

    trailing = state_with_three_clips()
    apply_timeline_edit(trailing, TimelineEdit(clip_id="v3", action="deactivate"))
    with pytest.raises(InvalidTimeError, match="no following clip"):
        apply_timeline_edit(
            trailing,
            TimelineEdit(clip_id="v3", action="recut", start_sec=2.0, end_sec=3.2),
        )


def test_recut_rejects_bounds_that_remove_a_neighbor() -> None:
    state = state_with_three_clips()
    apply_timeline_edit(state, TimelineEdit(clip_id="v2", action="deactivate"))

    with pytest.raises(InvalidTimeError, match="preceding clip"):
        apply_timeline_edit(
            state,
            TimelineEdit(clip_id="v2", action="recut", start_sec=0.0, end_sec=2.0),
        )
    with pytest.raises(InvalidTimeError, match="following clip"):
        apply_timeline_edit(
            state,
            TimelineEdit(clip_id="v2", action="recut", start_sec=1.0, end_sec=3.2),
        )


def test_recut_requires_a_known_inactive_clip_and_range() -> None:
    state = state_with_three_clips()
    apply_timeline_edit(state, TimelineEdit(clip_id="v2", action="deactivate"))

    with pytest.raises(InvalidTimeError, match="Unknown inactive"):
        apply_timeline_edit(
            state,
            TimelineEdit(clip_id="missing", action="recut", start_sec=1.0, end_sec=2.0),
        )
    with pytest.raises(InvalidTimeError, match="requires start and end"):
        apply_timeline_edit(state, TimelineEdit(clip_id="v2", action="recut"))
    with pytest.raises(InvalidTimeError, match="after start"):
        apply_timeline_edit(
            state,
            TimelineEdit(clip_id="v2", action="recut", start_sec=2.0, end_sec=1.0),
        )
