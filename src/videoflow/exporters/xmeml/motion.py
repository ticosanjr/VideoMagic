"""XMEML helper: transitions and fades."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from videoflow.domain.state import MediaInfo, VideoSegment

from .common import _append_rate


def _append_video_transition(
    parent: ET.Element,
    clip,
    media: MediaInfo,
    *,
    number: int,
) -> None:
    duration = clip.transition_out.duration_frames
    cut = clip.timeline_out_frame
    start = max(0, cut - duration // 2)
    item = ET.SubElement(parent, "transitionitem", {"id": f"videotrans-{number}"})
    ET.SubElement(item, "start").text = str(start)
    ET.SubElement(item, "end").text = str(start + duration)
    ET.SubElement(item, "alignment").text = "center"
    _append_rate(item, media)
    effect = ET.SubElement(item, "effect")
    name = "Cross Dissolve" if clip.transition_out.type == "crossfade" else "Fade to Black"
    ET.SubElement(effect, "name").text = name
    ET.SubElement(effect, "effectid").text = name
    ET.SubElement(effect, "effectcategory").text = "video"
    ET.SubElement(effect, "effecttype").text = "transition"
    ET.SubElement(effect, "mediatype").text = "video"

def _append_audio_fade(
    parent: ET.Element,
    media: MediaInfo,
    *,
    start: int,
    end: int,
    alignment: str,
    number: int,
) -> None:
    if end <= start:
        return
    item = ET.SubElement(parent, "transitionitem", {"id": f"audiofade-{number}-{alignment}"})
    ET.SubElement(item, "start").text = str(start)
    ET.SubElement(item, "end").text = str(end)
    ET.SubElement(item, "alignment").text = alignment
    _append_rate(item, media)
    effect = ET.SubElement(item, "effect")
    ET.SubElement(effect, "name").text = "Cross Fade ( 0dB)"
    ET.SubElement(effect, "effectid").text = "KGAudioTransCrossFade0dB"
    ET.SubElement(effect, "effectcategory").text = "audio"
    ET.SubElement(effect, "effecttype").text = "transition"
    ET.SubElement(effect, "mediatype").text = "audio"

def _append_motion(parent: ET.Element, clip: VideoSegment, media: MediaInfo) -> None:
    transform = clip.transform
    if (
        transform.scale == 1.0
        and not transform.keyframes
        and transform.pos_x == 0.0
        and transform.pos_y == 0.0
        and transform.anchor == "upper_third"
        and transform.pan_direction == "none"
    ):
        return
    filter_element = ET.SubElement(parent, "filter")
    effect = ET.SubElement(filter_element, "effect")
    ET.SubElement(effect, "name").text = "Basic Motion"
    ET.SubElement(effect, "effectid").text = "basicmotion"
    ET.SubElement(effect, "effectcategory").text = "motion"
    ET.SubElement(effect, "effecttype").text = "motion"
    ET.SubElement(effect, "mediatype").text = "video"
    scale = ET.SubElement(effect, "parameter")
    ET.SubElement(scale, "parameterid").text = "scale"
    ET.SubElement(scale, "name").text = "Scale"
    ET.SubElement(scale, "value").text = str(round(transform.scale * 100))
    center = ET.SubElement(effect, "parameter")
    ET.SubElement(center, "parameterid").text = "center"
    ET.SubElement(center, "name").text = "Center"
    ET.SubElement(center, "value").text = _motion_center(transform, media)
    if transform.keyframes:
        duration = max(1, clip.timeline_out_frame - clip.timeline_in_frame)
        for keyframe in transform.keyframes:
            key = ET.SubElement(scale, "keyframe")
            ET.SubElement(key, "when").text = str(round(keyframe.at * duration))
            ET.SubElement(key, "value").text = str(round(keyframe.scale * 100))
            position = ET.SubElement(center, "keyframe")
            ET.SubElement(position, "when").text = str(round(keyframe.at * duration))
            ET.SubElement(
                position, "value"
            ).text = f"{round(keyframe.pos_x * media.width)} {round(keyframe.pos_y * media.height)}"

def _motion_center(transform, media: MediaInfo) -> str:
    x = round(transform.pos_x * media.width)
    y = round(transform.pos_y * media.height)
    if transform.anchor == "upper_third":
        y -= media.height // 6
    if transform.pan_direction == "left_to_right":
        x -= media.width // 12
    elif transform.pan_direction == "right_to_left":
        x += media.width // 12
    return f"{x} {y}"
