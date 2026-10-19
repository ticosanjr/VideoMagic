"""FCP 7 XML (xmeml) for Adobe Premiere Pro.

Premiere does not import FCPXML. Video and audio are separate tracks so a J/L-cut
is two clipitems with different in/out points.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from videoflow.domain.state import MediaInfo, ProjectState, VideoSegment
from videoflow.domain.timebase import Rounding
from videoflow.exporters.common import (
    file_uri,
    require_timeline,
    timeline_duration_frames,
    write_text,
    xml_document,
)


def export_xmeml(state: ProjectState, output_path: Path) -> Path:
    """Write an FCP 7 XML timeline for Premiere Pro and return the artifact path."""

    media, video, audio = require_timeline(state)
    timebase = media.timebase()
    duration = timeline_duration_frames(state)

    root = ET.Element("xmeml", {"version": "5"})
    sequence = ET.SubElement(root, "sequence", {"id": "sequence-1"})
    ET.SubElement(sequence, "name").text = "VideoFlow"
    ET.SubElement(sequence, "duration").text = str(duration)
    _append_rate(sequence, media)

    media_element = ET.SubElement(sequence, "media")
    video_element = ET.SubElement(media_element, "video")
    format_element = ET.SubElement(video_element, "format")
    characteristics = ET.SubElement(format_element, "samplecharacteristics")
    ET.SubElement(characteristics, "width").text = str(media.width)
    ET.SubElement(characteristics, "height").text = str(media.height)
    ET.SubElement(characteristics, "anamorphic").text = "FALSE"
    ET.SubElement(characteristics, "pixelaspectratio").text = "square"
    ET.SubElement(characteristics, "fielddominance").text = "none"
    _append_rate(characteristics, media)

    video_track = ET.SubElement(video_element, "track")
    for index, clip in enumerate(state.video_segments):
        item = ET.SubElement(video_track, "clipitem", {"id": f"clipitem-{index + 1}"})
        ET.SubElement(item, "name").text = clip.clip_id
        ET.SubElement(item, "duration").text = str(media.duration_frames)
        _append_rate(item, media)
        ET.SubElement(item, "start").text = str(clip.timeline_in_frame)
        ET.SubElement(item, "end").text = str(clip.timeline_out_frame)
        ET.SubElement(item, "in").text = str(clip.source_in_frame)
        ET.SubElement(item, "out").text = str(clip.source_out_frame)
        _append_file(item, media, include_details=index == 0)
        _append_motion(item, clip)

    audio_element = ET.SubElement(media_element, "audio")
    audio_track = ET.SubElement(audio_element, "track")
    for index, clip in enumerate(state.audio_segments):
        item = ET.SubElement(audio_track, "clipitem", {"id": f"audioitem-{index + 1}"})
        ET.SubElement(item, "name").text = clip.clip_id
        ET.SubElement(item, "duration").text = str(media.duration_frames)
        _append_rate(item, media)
        ET.SubElement(item, "start").text = str(
            timebase.sample_to_frame(clip.timeline_in_sample, Rounding.NEAREST)
        )
        ET.SubElement(item, "end").text = str(
            timebase.sample_to_frame(clip.timeline_out_sample, Rounding.CEIL)
        )
        ET.SubElement(item, "in").text = str(
            timebase.sample_to_frame(clip.source_in_sample, Rounding.NEAREST)
        )
        ET.SubElement(item, "out").text = str(
            timebase.sample_to_frame(clip.source_out_sample, Rounding.CEIL)
        )
        source_track = ET.SubElement(item, "sourcetrack")
        ET.SubElement(source_track, "mediatype").text = "audio"
        ET.SubElement(source_track, "trackindex").text = "1"
        _append_file(item, media, include_details=False)

    return write_text(output_path, xml_document(root, "xmeml"))


def _append_rate(parent: ET.Element, media: MediaInfo) -> None:
    rate = ET.SubElement(parent, "rate")
    if media.fps_den == 1:
        ET.SubElement(rate, "timebase").text = str(media.fps_num)
        ET.SubElement(rate, "ntsc").text = "FALSE"
        return
    ET.SubElement(rate, "timebase").text = str(round(media.fps_num / media.fps_den))
    ET.SubElement(rate, "ntsc").text = "TRUE"


def _append_file(parent: ET.Element, media: MediaInfo, *, include_details: bool) -> None:
    file_element = ET.SubElement(parent, "file", {"id": "file-1"})
    if not include_details:
        return
    ET.SubElement(file_element, "name").text = Path(media.source_path).name
    ET.SubElement(file_element, "pathurl").text = file_uri(media.source_path)
    _append_rate(file_element, media)
    ET.SubElement(file_element, "duration").text = str(media.duration_frames)
    file_media = ET.SubElement(file_element, "media")
    ET.SubElement(file_media, "video")
    ET.SubElement(file_media, "audio")


def _append_motion(parent: ET.Element, clip: VideoSegment) -> None:
    transform = clip.transform
    if transform.scale == 1.0:
        return
    filter_element = ET.SubElement(parent, "filter")
    effect = ET.SubElement(filter_element, "effect")
    ET.SubElement(effect, "name").text = "Basic Motion"
    ET.SubElement(effect, "effectid").text = "basic"
    ET.SubElement(effect, "effectcategory").text = "motion"
    ET.SubElement(effect, "effecttype").text = "motion"
    ET.SubElement(effect, "mediatype").text = "video"
    parameter = ET.SubElement(effect, "parameter")
    ET.SubElement(parameter, "parameterid").text = "scale"
    ET.SubElement(parameter, "name").text = "Scale"
    ET.SubElement(parameter, "value").text = str(round(transform.scale * 100))
