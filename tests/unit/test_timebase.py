from fractions import Fraction
from typing import cast

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from videoflow.domain.errors import InvalidTimeError
from videoflow.domain.timebase import FrameSpan, Rounding, Timebase, _div, format_rational_time


def test_ntsc_frame_duration_is_the_1001_rational() -> None:
    timebase = Timebase(30000, 1001, 48000)
    assert timebase.frame_duration == Fraction(1001, 30000)
    assert timebase.format_frame_time(1) == "1001/30000s"
    assert timebase.format_frame_time(0) == "0s"


def test_frame_rate_is_reduced_by_gcd() -> None:
    timebase = Timebase(60, 2, 48000)
    assert (timebase.fps_num, timebase.fps_den) == (30, 1)


def test_sixty_minutes_of_30fps_has_no_float_drift() -> None:
    timebase = Timebase(30, 1, 48000)
    frames = 60 * 60 * 30
    assert timebase.frames_to_seconds(frames) == Fraction(3600)
    assert timebase.seconds_to_frames(Fraction(3600), Rounding.NEAREST) == frames
    total = sum((timebase.frame_duration for _ in range(1000)), Fraction(0))
    assert total == 1000 * timebase.frame_duration


def test_crossfade_default_is_960_samples_at_48k() -> None:
    timebase = Timebase(30, 1, 48000)
    assert timebase.milliseconds_to_samples(20) == 960


def test_pads_expand_to_covering_frames_and_clamp() -> None:
    timebase = Timebase(30, 1, 48000)
    padded = timebase.apply_pads(100, 200, 50, 80, media_duration_samples=250)
    assert padded.start_sample == 50
    assert padded.end_sample == 250
    assert timebase.frame_start_sample(padded.frames.start) <= padded.start_sample
    assert timebase.frame_start_sample(padded.frames.end) >= padded.end_sample


def test_pads_without_media_bound_and_leading_clamp() -> None:
    timebase = Timebase(24, 1, 16000)
    padded = timebase.apply_pads(10, 40, 100, 5)
    assert padded.start_sample == 0
    assert padded.end_sample == 45


def test_exact_frame_boundary_is_not_expanded_past_itself() -> None:
    timebase = Timebase(30, 1, 48000)
    span = timebase.expand_samples_to_frames(1600, 3200)
    assert (span.start, span.end) == (1, 2)


def test_frame_span_validates_and_reports_duration() -> None:
    span = FrameSpan(2, 5)
    assert span.duration_frames == 3
    with pytest.raises(InvalidTimeError):
        FrameSpan(-1, 2)
    with pytest.raises(InvalidTimeError):
        FrameSpan(4, 2)


def test_pads_reject_an_empty_span() -> None:
    timebase = Timebase(30, 1, 48000)
    with pytest.raises(InvalidTimeError):
        timebase.apply_pads(10, 10, 0, 0)


def test_rational_time_formatting() -> None:
    assert format_rational_time(Fraction(0)) == "0s"
    assert format_rational_time(Fraction(5, 1)) == "5s"
    assert format_rational_time(Fraction(2, 4)) == "1/2s"


def test_sample_and_frame_conversions_are_exact_round_trips() -> None:
    timebase = Timebase(30000, 1001, 48000)
    assert (
        timebase.seconds_to_samples(timebase.samples_to_seconds(123456), Rounding.NEAREST) == 123456
    )
    assert timebase.seconds_to_frames(timebase.frames_to_seconds(999), Rounding.FLOOR) == 999
    assert timebase.frame_to_sample(3, Rounding.FLOOR) == timebase.frame_start_sample(3)


def test_invalid_rates_raise() -> None:
    with pytest.raises(InvalidTimeError):
        Timebase(0, 1, 48000)
    with pytest.raises(InvalidTimeError):
        Timebase(30, -1, 48000)
    with pytest.raises(InvalidTimeError):
        Timebase(30, 1, 0)


def test_negative_and_bool_times_are_rejected() -> None:
    timebase = Timebase(30, 1, 48000)
    with pytest.raises(InvalidTimeError):
        timebase.frames_to_seconds(-1)
    with pytest.raises(InvalidTimeError):
        timebase.samples_to_seconds(cast(int, True))
    with pytest.raises(InvalidTimeError):
        timebase.seconds_to_frames(Fraction(-1), Rounding.FLOOR)
    with pytest.raises(InvalidTimeError):
        timebase.expand_samples_to_frames(10, 10)
    with pytest.raises(InvalidTimeError):
        timebase.apply_pads(0, 10, 0, 0, media_duration_samples=0)
    with pytest.raises(InvalidTimeError):
        format_rational_time(Fraction(-1, 2))
    with pytest.raises(InvalidTimeError):
        timebase.milliseconds_to_samples(-5)


def test_private_division_edges() -> None:
    assert _div(7, 3, Rounding.FLOOR) == 2
    assert _div(7, 3, Rounding.CEIL) == 3
    assert _div(6, 4, Rounding.NEAREST) == 2
    assert _div(1, 4, Rounding.NEAREST) == 0
    with pytest.raises(InvalidTimeError):
        _div(1, 0, Rounding.FLOOR)
    with pytest.raises(InvalidTimeError):
        _div(-1, 2, Rounding.FLOOR)
    with pytest.raises(InvalidTimeError):
        _div(1, 2, cast(Rounding, "sideways"))


@given(
    fps_num=st.integers(min_value=1, max_value=60000),
    fps_den=st.integers(min_value=1, max_value=1001),
    rate=st.sampled_from([8000, 16000, 44100, 48000]),
    frame=st.integers(min_value=0, max_value=200_000),
    sample=st.integers(min_value=0, max_value=200_000),
)
@settings(max_examples=40)
def test_rational_round_trips(
    fps_num: int,
    fps_den: int,
    rate: int,
    frame: int,
    sample: int,
) -> None:
    timebase = Timebase(fps_num, fps_den, rate)
    assert timebase.seconds_to_frames(timebase.frames_to_seconds(frame), Rounding.NEAREST) == frame
    assert (
        timebase.seconds_to_samples(timebase.samples_to_seconds(sample), Rounding.NEAREST) == sample
    )


@given(
    start=st.integers(min_value=0, max_value=50_000),
    length=st.integers(min_value=1, max_value=20_000),
)
@settings(max_examples=30)
def test_expanded_frames_cover_the_sample_span(start: int, length: int) -> None:
    timebase = Timebase(30000, 1001, 48000)
    end = start + length
    span = timebase.expand_samples_to_frames(start, end)
    assert timebase.frame_start_sample(span.start) <= start
    assert timebase.frame_start_sample(span.end) >= end
