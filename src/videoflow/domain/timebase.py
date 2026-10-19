"""Rational media time.

Float seconds are a display convenience. Cuts, fades, and exports use integers:
video on frame indices, audio on sample indices. A frame duration is the
fraction ``fps_den / fps_num`` (so 29.97 is 1001/30000, never 0.0333667).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from math import gcd

from videoflow.domain.errors import InvalidTimeError


class Rounding(StrEnum):
    """Integer division policy for non-negative times."""

    FLOOR = "floor"
    CEIL = "ceil"
    NEAREST = "nearest"


def _div(numerator: int, denominator: int, rounding: Rounding) -> int:
    if denominator <= 0:
        raise InvalidTimeError("denominator must be positive")
    if numerator < 0:
        raise InvalidTimeError("time values must be non-negative")
    if rounding is Rounding.FLOOR:
        return numerator // denominator
    if rounding is Rounding.CEIL:
        return -(-numerator // denominator)
    if rounding is Rounding.NEAREST:
        return (numerator + denominator // 2) // denominator
    raise InvalidTimeError(f"unknown rounding: {rounding}")


def format_rational_time(seconds: Fraction) -> str:
    """Format a non-negative duration the way FCPXML expects (``1001/30000s``)."""

    value = Fraction(seconds)
    if value < 0:
        raise InvalidTimeError("cannot format a negative time")
    if value == 0:
        return "0s"
    if value.denominator == 1:
        return f"{value.numerator}s"
    return f"{value.numerator}/{value.denominator}s"


@dataclass(frozen=True, slots=True)
class FrameSpan:
    """Inclusive start frame and exclusive end frame."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise InvalidTimeError("invalid frame span")

    @property
    def duration_frames(self) -> int:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class PaddedSpan:
    """Speech interval after sample pads, plus the video frames that cover it."""

    start_sample: int
    end_sample: int
    frames: FrameSpan


@dataclass(frozen=True, slots=True)
class Timebase:
    """Declared video rate and audio sample rate for one source.

    ``fps_num / fps_den`` is the frame rate. Values are reduced by their gcd,
    so ``60/2`` becomes ``30/1``. ``30000/1001`` is already reduced and stays
    as the NTSC timebase.
    """

    fps_num: int
    fps_den: int
    audio_sample_rate: int

    def __post_init__(self) -> None:
        if self.fps_num <= 0 or self.fps_den <= 0:
            raise InvalidTimeError("frame rate must be a positive rational")
        if self.audio_sample_rate <= 0:
            raise InvalidTimeError("audio sample rate must be positive")
        divisor = gcd(self.fps_num, self.fps_den)
        if divisor != 1:
            object.__setattr__(self, "fps_num", self.fps_num // divisor)
            object.__setattr__(self, "fps_den", self.fps_den // divisor)

    @property
    def frame_duration(self) -> Fraction:
        return Fraction(self.fps_den, self.fps_num)

    def frames_to_seconds(self, frames: int) -> Fraction:
        self._require_non_negative(frames, "frame")
        return frames * self.frame_duration

    def seconds_to_frames(self, seconds: Fraction, rounding: Rounding) -> int:
        value = self._require_seconds(seconds)
        return _div(value.numerator * self.fps_num, value.denominator * self.fps_den, rounding)

    def samples_to_seconds(self, samples: int) -> Fraction:
        self._require_non_negative(samples, "sample")
        return Fraction(samples, self.audio_sample_rate)

    def seconds_to_samples(self, seconds: Fraction, rounding: Rounding) -> int:
        value = self._require_seconds(seconds)
        return _div(value.numerator * self.audio_sample_rate, value.denominator, rounding)

    def milliseconds_to_samples(
        self, milliseconds: int, rounding: Rounding = Rounding.NEAREST
    ) -> int:
        self._require_non_negative(milliseconds, "millisecond")
        return _div(milliseconds * self.audio_sample_rate, 1000, rounding)

    def frame_start_sample(self, frame: int) -> int:
        """First sample index of ``frame``, floored when the boundary is not integral."""

        self._require_non_negative(frame, "frame")
        return (frame * self.audio_sample_rate * self.fps_den) // self.fps_num

    def frame_to_sample(self, frame: int, rounding: Rounding) -> int:
        self._require_non_negative(frame, "frame")
        return _div(frame * self.audio_sample_rate * self.fps_den, self.fps_num, rounding)

    def sample_to_frame(self, sample: int, rounding: Rounding) -> int:
        self._require_non_negative(sample, "sample")
        return _div(sample * self.fps_num, self.audio_sample_rate * self.fps_den, rounding)

    def format_frame_time(self, frame: int) -> str:
        return format_rational_time(self.frames_to_seconds(frame))

    def expand_samples_to_frames(self, start_sample: int, end_sample: int) -> FrameSpan:
        """Smallest frame span that fully covers ``[start_sample, end_sample)``.

        The start snaps down and the end snaps up, so a pad is never clipped
        by landing inside a frame.
        """

        self._require_non_negative(start_sample, "sample")
        self._require_non_negative(end_sample, "sample")
        if end_sample <= start_sample:
            raise InvalidTimeError("sample span must be non-empty")
        start_frame = self.sample_to_frame(start_sample, Rounding.FLOOR)
        end_frame = self.sample_to_frame(end_sample, Rounding.CEIL)
        return FrameSpan(start_frame, end_frame)

    def apply_pads(
        self,
        start_sample: int,
        end_sample: int,
        pad_before_samples: int,
        pad_after_samples: int,
        media_duration_samples: int | None = None,
    ) -> PaddedSpan:
        """Apply audio pads, clamp to the media, then expand to covering frames."""

        self._require_non_negative(start_sample, "sample")
        self._require_non_negative(end_sample, "sample")
        self._require_non_negative(pad_before_samples, "pad")
        self._require_non_negative(pad_after_samples, "pad")
        if end_sample <= start_sample:
            raise InvalidTimeError("sample span must be non-empty")
        padded_start = max(0, start_sample - pad_before_samples)
        padded_end = end_sample + pad_after_samples
        if media_duration_samples is not None:
            self._require_non_negative(media_duration_samples, "duration")
            padded_end = min(media_duration_samples, padded_end)
            padded_start = min(padded_start, media_duration_samples)
        if padded_end <= padded_start:
            raise InvalidTimeError("pads collapsed the span against the media bounds")
        frames = self.expand_samples_to_frames(padded_start, padded_end)
        return PaddedSpan(padded_start, padded_end, frames)

    def _require_non_negative(self, value: int, label: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise InvalidTimeError(f"{label} must be a non-negative integer")

    def _require_seconds(self, seconds: Fraction) -> Fraction:
        value = Fraction(seconds)
        if value < 0:
            raise InvalidTimeError("seconds must be non-negative")
        return value
