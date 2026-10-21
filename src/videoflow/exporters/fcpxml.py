"""FCPXML for DaVinci Resolve.

J/L-cuts use ``audioStart`` and ``audioDuration`` on the composite asset-clip,
which is the FCPXML mechanism for offsetting audio from its own picture.
Audio fade edges use keyframed ``adjust-volume`` ramps. Keyframed progressive
zooms are not emitted yet; see ``docs/exporters.md``.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from typing import Literal

from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.domain.timebase import Rounding, format_rational_time
from videoflow.exporters.common import (
    file_uri,
    require_timeline,
    timeline_duration_frames,
    timeline_duration_samples,
    write_text,
    xml_document,
)

Dialect = Literal["1.9", "1.10"]


def export_fcpxml(state: ProjectState, output_path: Path, *, dialect: Dialect = "1.9") -> Path:
    """Write an FCPXML timeline for Resolve and return the artifact path."""

    if dialect not in ("1.9", "1.10"):
        raise ValueError(f"Unsupported FCPXML dialect: {dialect}")
    media, _, audio = require_timeline(state)
    timebase = media.timebase()
    duration_frames = max(
        timeline_duration_frames(state),
        timebase.sample_to_frame(timeline_duration_samples(state), Rounding.CEIL),
    )

    root = ET.Element("fcpxml", {"version": dialect})
    resources = ET.SubElement(root, "resources")
    ET.SubElement(
        resources,
        "format",
        {
            "id": "r1",
            "name": f"FFVideoFormat{media.width}x{media.height}p{_rate_label(media)}",
            "frameDuration": format_rational_time(timebase.frame_duration),
            "width": str(media.width),
            "height": str(media.height),
        },
    )
    asset = ET.SubElement(
        resources,
        "asset",
        {
            "id": "a1",
            "name": Path(media.source_path).name,
            "start": "0s",
            "duration": format_rational_time(timebase.frames_to_seconds(media.duration_frames)),
            "hasVideo": "1",
            "videoSources": "1",
            "hasAudio": "1",
            "format": "r1",
            "audioSources": "1",
            "audioChannels": "1",
            "audioRate": str(media.audio_sample_rate),
        },
    )
    # FCPXML 1.9 moved the original media URL to media-rep. Resolve rejects the
    # old asset src form even though it is still valid for FCPXML 1.8.
    ET.SubElement(
        asset,
        "media-rep",
        {"kind": "original-media", "src": file_uri(media.source_path)},
    )

    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", {"name": "VideoFlow"})
    project = ET.SubElement(event, "project", {"name": "VideoFlow"})
    sequence_attrs = {
        "format": "r1",
        "duration": format_rational_time(timebase.frames_to_seconds(duration_frames)),
        "tcStart": "0s",
        "tcFormat": _tc_format(media),
        "audioLayout": "mono",
    }
    audio_rate = _audio_rate_label(media.audio_sample_rate)
    if audio_rate is not None:
        sequence_attrs["audioRate"] = audio_rate
    sequence = ET.SubElement(project, "sequence", sequence_attrs)
    spine = ET.SubElement(sequence, "spine")

    for clip in state.video_segments:
        audio_clip = audio[clip.clip_id]
        element = ET.SubElement(
            spine,
            "asset-clip",
            {
                "ref": "a1",
                "name": clip.clip_id,
                "offset": format_rational_time(timebase.frames_to_seconds(clip.timeline_in_frame)),
                "start": format_rational_time(timebase.frames_to_seconds(clip.source_in_frame)),
                "duration": format_rational_time(
                    timebase.frames_to_seconds(clip.source_out_frame - clip.source_in_frame)
                ),
                "audioStart": format_rational_time(
                    timebase.samples_to_seconds(audio_clip.source_in_sample)
                ),
                "audioDuration": format_rational_time(
                    timebase.samples_to_seconds(
                        audio_clip.source_out_sample - audio_clip.source_in_sample
                    )
                ),
                "srcEnable": "all",
                "audioRole": "dialogue",
            },
        )
        _append_transform(element, clip, media)
        _append_audio_fade(element, audio_clip, media)

    return write_text(output_path, xml_document(root, "fcpxml"))


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
