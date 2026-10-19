"""FCPXML for DaVinci Resolve.

J/L-cuts use ``audioStart`` and ``audioDuration`` on the composite asset-clip,
which is the FCPXML mechanism for offsetting audio from its own picture.
Transitions and keyframed progressive zooms are not emitted yet; see
``docs/exporters.md``.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal

from videoflow.domain.state import MediaInfo, ProjectState, VideoSegment
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
    ET.SubElement(
        resources,
        "asset",
        {
            "id": "a1",
            "name": Path(media.source_path).name,
            "src": file_uri(media.source_path),
            "start": "0s",
            "duration": format_rational_time(timebase.frames_to_seconds(media.duration_frames)),
            "hasVideo": "1",
            "hasAudio": "1",
            "format": "r1",
            "audioSources": "1",
            "audioChannels": "1",
            "audioRate": str(media.audio_sample_rate),
        },
    )

    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", {"name": "VideoFlow"})
    project = ET.SubElement(event, "project", {"name": "VideoFlow"})
    sequence = ET.SubElement(
        project,
        "sequence",
        {
            "format": "r1",
            "duration": format_rational_time(timebase.frames_to_seconds(duration_frames)),
            "tcStart": "0s",
            "tcFormat": _tc_format(media),
        },
    )
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
            },
        )
        _append_transform(element, clip, media)

    return write_text(output_path, xml_document(root, "fcpxml"))


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


def _rate_label(media: MediaInfo) -> str:
    if media.fps_den == 1:
        return str(media.fps_num)
    return str(round(media.fps_num / media.fps_den))


def _tc_format(media: MediaInfo) -> str:
    drop_frame = media.fps_den == 1001 and media.fps_num % 1001 == 0
    return "DF" if drop_frame else "NDF"
