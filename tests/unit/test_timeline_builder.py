import pytest

from videoflow.application.timeline_builder import (
    _Clip,
    _jcut_shift,
    _lcut_shift,
    build_timeline,
)
from videoflow.domain.config import JlCutsConfig, ZoomsConfig
from videoflow.domain.errors import InvalidTimeError
from videoflow.domain.state import MediaInfo
from videoflow.domain.timeline import is_packed


def media(frames: int = 90, *, fps_num: int = 30, fps_den: int = 1, rate: int = 48000) -> MediaInfo:
    return MediaInfo(
        source_path="/media/source.mp4",
        duration_frames=frames,
        fps_num=fps_num,
        fps_den=fps_den,
        width=1920,
        height=1080,
        audio_sample_rate=rate,
    )


def test_straight_cuts_are_frame_quantised_and_packed() -> None:
    result = build_timeline(
        media(),
        [(0, 48000), (96000, 144000)],
        jl=JlCutsConfig(enable_j_cuts=False),
        zooms=ZoomsConfig(mode="manual_rules"),
    )
    assert [(item.source_in_frame, item.source_out_frame) for item in result.video_segments] == [
        (0, 30),
        (60, 90),
    ]
    assert [
        (item.timeline_in_sample, item.timeline_out_sample) for item in result.audio_segments
    ] == [(0, 48000), (48000, 96000)]
    assert is_packed(
        [(item.timeline_in_frame, item.timeline_out_frame) for item in result.video_segments]
    )


def test_jcut_moves_the_audio_cut_earlier_and_keeps_contiguity() -> None:
    result = build_timeline(
        media(),
        [(0, 48000), (96000, 144000)],
        jl=JlCutsConfig(
            enable_j_cuts=True, offset_ms=200, fade_in_ms=0, fade_out_ms=0
        ),
        zooms=ZoomsConfig(mode="manual_rules"),
    )
    left, right = result.audio_segments
    assert left.source_out_sample == 48000 - 9600
    assert left.timeline_out_sample == 48000 - 9600
    assert right.source_in_sample == 96000 - 9600
    assert right.timeline_in_sample == left.timeline_out_sample
    assert left.fade_out_samples == 960
    assert right.fade_in_samples == 960
    assert left.fade_in_samples == 0
    assert right.fade_out_samples == 0


def test_lcut_moves_the_audio_cut_later() -> None:
    result = build_timeline(
        media(),
        [(0, 48000), (96000, 144000)],
        jl=JlCutsConfig(enable_j_cuts=False, enable_l_cuts=True, offset_ms=200),
        zooms=ZoomsConfig(mode="manual_rules"),
    )
    left, right = result.audio_segments
    assert left.source_out_sample == 48000 + 9600
    assert left.timeline_out_sample == 48000 + 9600
    assert right.source_in_sample == 96000 + 9600
    assert right.timeline_in_sample == left.timeline_out_sample


def test_short_handle_keeps_a_straight_cut() -> None:
    result = build_timeline(
        media(frames=60),
        [(0, 48000), (48480, 96000)],
        jl=JlCutsConfig(enable_j_cuts=True, offset_ms=200),
        zooms=ZoomsConfig(mode="manual_rules"),
    )
    assert result.audio_segments[0].source_out_sample == 48000
    assert any("handle was too small" in warning for warning in result.warnings)


def test_handle_check_off_clamps_instead_of_skipping() -> None:
    result = build_timeline(
        media(frames=60),
        [(0, 48000), (49600, 96000)],
        jl=JlCutsConfig(enable_j_cuts=True, offset_ms=200, handle_check=False),
        zooms=ZoomsConfig(mode="manual_rules"),
    )
    assert result.audio_segments[0].source_out_sample == 48000 - 1600
    assert result.audio_segments[1].timeline_in_sample == 48000 - 1600


def test_jcut_wins_when_both_are_enabled() -> None:
    result = build_timeline(
        media(),
        [(0, 48000), (96000, 144000)],
        jl=JlCutsConfig(enable_j_cuts=True, enable_l_cuts=True),
        zooms=ZoomsConfig(mode="manual_rules"),
    )
    assert result.audio_segments[0].source_out_sample == 48000 - 9600
    assert any("J-cut wins" in warning for warning in result.warnings)


def test_overlapping_and_touching_spans_are_merged() -> None:
    result = build_timeline(
        media(),
        [(0, 48000), (47000, 96000), (96000, 110000)],
        jl=JlCutsConfig(enable_j_cuts=False),
        zooms=ZoomsConfig(mode="manual_rules"),
    )
    assert len(result.video_segments) == 1
    assert result.video_segments[0].source_in_frame == 0
    assert result.video_segments[0].source_out_frame == 69


def test_zooms_alternate_and_respect_manual_and_face_fallback() -> None:
    result = build_timeline(
        media(frames=90),
        [(0, 24000), (48000, 72000), (96000, 120000)],
        jl=JlCutsConfig(enable_j_cuts=False),
        zooms=ZoomsConfig(
            mode="alternate_cuts",
            punch_in_scale=1.2,
            anchor_point="face_detect",
            progressive_zoom=True,
        ),
    )
    assert result.video_segments[0].transform.scale == 1.0
    assert result.video_segments[1].transform.scale == 1.2
    assert result.video_segments[1].transform.type == "slow_zoom_in"
    assert [item.scale for item in result.video_segments[1].transform.keyframes] == [1.0, 1.2]
    assert any("face detection" in warning for warning in result.warnings)


def test_lecture_preset_style_zooms_are_neutral() -> None:
    result = build_timeline(
        media(),
        [(0, 24000), (24000, 48000)],
        jl=JlCutsConfig(enable_j_cuts=False),
        zooms=ZoomsConfig(mode="manual_rules", progressive_zoom=False),
    )
    assert all(item.transform.scale == 1.0 for item in result.video_segments)


def test_empty_spans_fail_instead_of_exporting_an_empty_timeline() -> None:
    with pytest.raises(InvalidTimeError):
        build_timeline(
            media(),
            [],
            jl=JlCutsConfig(),
            zooms=ZoomsConfig(),
        )


def test_spans_outside_the_media_are_clamped() -> None:
    result = build_timeline(
        media(frames=30),
        [(-100, 16000), (32000, 48000)],
        jl=JlCutsConfig(enable_j_cuts=False),
        zooms=ZoomsConfig(mode="manual_rules"),
    )
    assert result.video_segments[0].source_in_frame == 0
    assert result.video_segments[-1].source_out_frame == 30
    assert result.audio_segments[-1].source_out_sample <= 48000


def test_pan_without_zoom_is_recorded_as_a_pan() -> None:
    result = build_timeline(
        media(),
        [(0, 24000), (48000, 72000)],
        jl=JlCutsConfig(enable_j_cuts=False),
        zooms=ZoomsConfig(mode="manual_rules", pan_direction="left_to_right"),
    )
    assert result.video_segments[0].transform.type == "pan"
    assert result.video_segments[0].transform.pan_direction == "left_to_right"


def test_an_inverted_span_is_rejected() -> None:
    with pytest.raises(InvalidTimeError, match="ends before"):
        build_timeline(media(), [(100, 50)], jl=JlCutsConfig(), zooms=ZoomsConfig())


def test_zero_length_media_fails_cleanly() -> None:
    with pytest.raises(InvalidTimeError):
        build_timeline(media(frames=0), [(0, 1000)], jl=JlCutsConfig(), zooms=ZoomsConfig())


def test_lcut_with_a_small_gap_falls_back_to_a_straight_cut() -> None:
    result = build_timeline(
        media(frames=60),
        [(0, 48000), (49600, 96000)],
        jl=JlCutsConfig(enable_j_cuts=False, enable_l_cuts=True, offset_ms=200),
        zooms=ZoomsConfig(mode="manual_rules"),
    )
    assert result.audio_segments[0].source_out_sample == 48000
    assert any("handle was too small" in warning for warning in result.warnings)


def _clip(*, as_in: int, as_out: int, ts_in: int, ts_out: int) -> _Clip:
    return _Clip(
        clip_id="c",
        vf_in=0,
        vf_out=30,
        tf_in=0,
        tf_out=30,
        as_in=as_in,
        as_out=as_out,
        ts_in=ts_in,
        ts_out=ts_out,
        orig_as_in=as_in,
        orig_as_out=as_out,
    )


def test_jcut_shift_edge_guards() -> None:
    left = _clip(as_in=0, as_out=1000, ts_in=0, ts_out=1000)
    right = _clip(as_in=2000, as_out=3000, ts_in=1000, ts_out=2000)
    assert _jcut_shift(left, right, 100, 1000, True) == 100
    assert _jcut_shift(left, right, 100, 50, True) is None
    assert (
        _jcut_shift(_clip(as_in=0, as_out=40, ts_in=0, ts_out=40), right, 100, 1000, False) is None
    )
    assert (
        _jcut_shift(left, _clip(as_in=2000, as_out=3000, ts_in=20, ts_out=2000), 100, 1000, False)
        is None
    )
    assert (
        _jcut_shift(left, _clip(as_in=50, as_out=3000, ts_in=1000, ts_out=2000), 100, 1000, False)
        is None
    )


def test_lcut_shift_edge_guards() -> None:
    left = _clip(as_in=0, as_out=1000, ts_in=0, ts_out=1000)
    right = _clip(as_in=2000, as_out=3000, ts_in=1000, ts_out=2000)
    assert _lcut_shift(left, right, 100, 1000, 5000, True) == 100
    assert _lcut_shift(left, right, 100, 50, 5000, True) is None
    assert _lcut_shift(left, right, 100, 1000, 1050, True) is None
    assert (
        _lcut_shift(
            left, _clip(as_in=1950, as_out=2000, ts_in=1000, ts_out=2000), 100, 1000, 5000, False
        )
        is None
    )
    assert (
        _lcut_shift(
            left, _clip(as_in=2000, as_out=3000, ts_in=1900, ts_out=2000), 100, 1000, 5000, False
        )
        is None
    )


def test_topic_change_warns_about_its_approximation() -> None:
    result = build_timeline(
        media(),
        [(0, 24000), (24000, 48000)],
        jl=JlCutsConfig(enable_j_cuts=False),
        zooms=ZoomsConfig(mode="topic_change"),
    )
    assert any("topic_change" in warning for warning in result.warnings)
