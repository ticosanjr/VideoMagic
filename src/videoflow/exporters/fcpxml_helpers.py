"""Shared FCPXML temporal and audio helpers."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction

from videoflow.domain.state import AudioSegment, MediaInfo, VideoSegment
from videoflow.domain.timebase import format_rational_time


def _seconds(value: float) -> Fraction:
    return Fraction(str(max(0.0, value))).limit_denominator(1_000_000)

def _append_music_volume(element: ET.Element, entry) -> None:
    """Write a gain envelope with ducking ramps around each speech range."""

    points: list[tuple[Fraction, float]] = [(Fraction(0), entry.gain_db)]
    for start, end, level in entry.duck_ranges:
        local_start = max(0.0, start - entry.start_sec)
        local_end = min(entry.duration_sec, end - entry.start_sec)
        if local_end <= local_start:
            continue
        ducked = entry.gain_db + level
        ramp = 0.15
        points.extend(
            [
                (_seconds(local_start), entry.gain_db),
                (_seconds(min(local_end, local_start + ramp)), ducked),
                (_seconds(max(local_start, local_end - ramp)), ducked),
                (_seconds(local_end), entry.gain_db),
            ]
        )
    points.append((_seconds(entry.duration_sec), entry.gain_db))
    ordered: list[tuple[Fraction, float]] = []
    for time, value in points:
        if ordered and ordered[-1][0] == time:
            ordered[-1] = (time, value)
        else:
            ordered.append((time, value))
    adjustment = ET.SubElement(element, "adjust-volume")
    parameter = ET.SubElement(adjustment, "param", {"name": "amount"})
    animation = ET.SubElement(parameter, "keyframeAnimation")
    for time, value in ordered:
        ET.SubElement(
            animation,
            "keyframe",
            {
                "time": format_rational_time(time),
                "value": f"{value:g}dB",
                "interp": "linear",
            },
        )

def _append_audio_fade(element: ET.Element, clip: AudioSegment, media: MediaInfo) -> None:
    fade_in_samples = clip.fade_in_samples
    fade_out_samples = clip.fade_out_samples
    if fade_in_samples <= 0 and fade_out_samples <= 0:
        return
    timebase = media.timebase()
    duration_samples = clip.source_out_sample - clip.source_in_sample
    duration = timebase.samples_to_seconds(duration_samples)
    fade_in = min(timebase.samples_to_seconds(fade_in_samples), duration)
    fade_out = min(timebase.samples_to_seconds(fade_out_samples), duration - fade_in)
    points: list[tuple[Fraction, str]] = []
    if fade_in > 0:
        points.extend([(Fraction(0), "-60dB"), (fade_in, "0dB")])
    else:
        points.append((Fraction(0), "0dB"))
    if fade_out > 0:
        points.extend([(duration - fade_out, "0dB"), (duration, "-60dB")])
    else:
        points.append((duration, "0dB"))
    # Keep the last value for a repeated timestamp, then emit in time order.
    ordered: list[tuple[Fraction, str]] = []
    for time, value in points:
        if ordered and ordered[-1][0] == time:
            ordered[-1] = (time, value)
        else:
            ordered.append((time, value))
    adjustment = ET.SubElement(element, "adjust-volume")
    parameter = ET.SubElement(adjustment, "param", {"name": "amount"})
    animation = ET.SubElement(parameter, "keyframeAnimation")
    for time, value in ordered:
        ET.SubElement(
            animation,
            "keyframe",
            {
                "time": format_rational_time(time),
                "value": value,
                "interp": "linear",
            },
        )

def _append_transform(element: ET.Element, clip: VideoSegment, media: MediaInfo) -> None:
    transform = clip.transform
    if transform.keyframes:
        adjustment = ET.SubElement(element, "adjust-transform", {"enabled": "1"})
        parameter = ET.SubElement(adjustment, "param", {"name": "scale"})
        animation = ET.SubElement(parameter, "keyframeAnimation")
        duration = max(1, clip.timeline_out_frame - clip.timeline_in_frame)
        timebase = media.timebase()
        for keyframe in transform.keyframes:
            frame = round(keyframe.at * duration)
            ET.SubElement(
                animation,
                "keyframe",
                {
                    "time": format_rational_time(timebase.frames_to_seconds(frame)),
                    "value": f"{keyframe.scale:g}",
                    "curve": keyframe.curve,
                },
            )
        return
    if transform.scale == 1.0 and transform.type == "none" and transform.pan_direction == "none":
        return
    x = 0
    y = 0
    if transform.anchor == "upper_third":
        y = media.height // 6
    if transform.pan_direction == "left_to_right":
        x = -(media.width // 12)
    elif transform.pan_direction == "right_to_left":
        x = media.width // 12
    x += round(transform.pos_x * media.width)
    y += round(transform.pos_y * media.height)
    ET.SubElement(
        element,
        "adjust-transform",
        {
            "scale": f"{transform.scale} {transform.scale}",
            "position": f"{x} {y}",
        },
    )

def _audio_rate_label(sample_rate: int) -> str | None:
    return {
        32000: "32k",
        44100: "44.1k",
        48000: "48k",
        88200: "88.2k",
        96000: "96k",
        176400: "176.4k",
        192000: "192k",
    }.get(sample_rate)

def _rate_label(media: MediaInfo) -> str:
    if media.fps_den == 1:
        return str(media.fps_num)
    return str(round(media.fps_num / media.fps_den))

def _tc_format(media: MediaInfo) -> str:
    drop_frame = media.fps_den == 1001 and media.fps_num % 1001 == 0
    return "DF" if drop_frame else "NDF"
