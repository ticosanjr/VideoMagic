"""XMEML helper: shared XML primitives."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from videoflow.domain.state import MediaInfo
from videoflow.exporters.common import (
    file_uri,
)


def _append_sequence_timecode(sequence: ET.Element, media: MediaInfo) -> None:
    timecode = ET.SubElement(sequence, "timecode")
    _append_rate(timecode, media)
    ET.SubElement(timecode, "frame").text = "0"
    ET.SubElement(timecode, "displayformat").text = "NDF"

def _append_rate(parent: ET.Element, media: MediaInfo) -> None:
    rate = ET.SubElement(parent, "rate")
    if media.fps_den == 1:
        ET.SubElement(rate, "timebase").text = str(media.fps_num)
        ET.SubElement(rate, "ntsc").text = "FALSE"
        return
    ET.SubElement(rate, "timebase").text = str(round(media.fps_num / media.fps_den))
    ET.SubElement(rate, "ntsc").text = "TRUE"

def _append_video_characteristics(parent: ET.Element, media: MediaInfo) -> None:
    ET.SubElement(parent, "width").text = str(media.width)
    ET.SubElement(parent, "height").text = str(media.height)
    ET.SubElement(parent, "anamorphic").text = "FALSE"
    ET.SubElement(parent, "pixelaspectratio").text = "square"
    ET.SubElement(parent, "fielddominance").text = "none"
    _append_rate(parent, media)

def _append_audio_format(parent: ET.Element, media: MediaInfo) -> None:
    format_element = ET.SubElement(parent, "format")
    characteristics = ET.SubElement(format_element, "samplecharacteristics")
    ET.SubElement(characteristics, "depth").text = "16"
    ET.SubElement(characteristics, "samplerate").text = str(media.audio_sample_rate)

def _append_file(parent: ET.Element, media: MediaInfo, *, file_id: str) -> None:
    file_element = ET.SubElement(parent, "file", {"id": file_id})
    ET.SubElement(file_element, "name").text = Path(media.source_path).name
    ET.SubElement(file_element, "pathurl").text = _premiere_path_url(media.source_path)
    _append_rate(file_element, media)
    ET.SubElement(file_element, "duration").text = str(media.duration_frames)
    file_media = ET.SubElement(file_element, "media")
    video = ET.SubElement(file_media, "video")
    characteristics = ET.SubElement(video, "samplecharacteristics")
    _append_video_characteristics(characteristics, media)
    audio = ET.SubElement(file_media, "audio")
    _append_audio_format(audio, media)
    ET.SubElement(audio, "channelcount").text = "1"

def _append_link(
    parent: ET.Element,
    reference: str,
    media_type: str,
    clip_index: int,
) -> None:
    link = ET.SubElement(parent, "link")
    ET.SubElement(link, "linkclipref").text = reference
    ET.SubElement(link, "mediatype").text = media_type
    ET.SubElement(link, "trackindex").text = "1"
    ET.SubElement(link, "clipindex").text = str(clip_index)
    ET.SubElement(link, "groupindex").text = str(clip_index)

def _premiere_path_url(path: str) -> str:
    """Return the FCP 7 file URL form Premiere expects on macOS and Windows."""

    uri = file_uri(path)
    prefix = "file:///"
    if not uri.startswith(prefix):
        return uri
    rest = uri[len(prefix) :]
    if len(rest) >= 2 and rest[1] == ":" and rest[0].isalpha():
        rest = f"{rest[0]}%3a{rest[2:]}"
    return f"file://localhost/{rest}"

def _append_color_filter(item: ET.Element) -> None:
    filter_element = ET.SubElement(item, "filter")
    effect = ET.SubElement(filter_element, "effect")
    ET.SubElement(effect, "name").text = "Color Correction"
    ET.SubElement(effect, "effectid").text = "colorCorrect"
    ET.SubElement(effect, "effectcategory").text = "video"
    ET.SubElement(effect, "effecttype").text = "filter"
    ET.SubElement(effect, "mediatype").text = "video"

def _append_basic_motion(item: ET.Element, entry, media: MediaInfo) -> None:
    if not (entry.width and entry.height and entry.source_width and entry.source_height):
        return
    effect = ET.SubElement(item, "filter")
    effect_element = ET.SubElement(effect, "effect")
    ET.SubElement(effect_element, "name").text = "Basic Motion"
    ET.SubElement(effect_element, "effectid").text = "basic"
    ET.SubElement(effect_element, "effectcategory").text = "motion"
    ET.SubElement(effect_element, "effecttype").text = "motion"
    ET.SubElement(effect_element, "mediatype").text = "video"
    scale = ET.SubElement(effect_element, "parameter")
    ET.SubElement(scale, "parameterid").text = "scale"
    ET.SubElement(scale, "name").text = "Scale"
    ET.SubElement(scale, "value").text = f"{entry.width / entry.source_width * 100:.3f}"
    center = ET.SubElement(effect_element, "parameter")
    ET.SubElement(center, "parameterid").text = "center"
    ET.SubElement(center, "name").text = "Center"
    value = ET.SubElement(center, "value")
    ET.SubElement(value, "horiz").text = f"{entry.x + entry.width / 2 - media.width / 2:.3f}"
    ET.SubElement(value, "vert").text = f"{entry.y + entry.height / 2 - media.height / 2:.3f}"
