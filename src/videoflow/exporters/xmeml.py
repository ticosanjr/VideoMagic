"""FCP 7 XML (xmeml) for Adobe Premiere Pro.

Premiere's reliable interchange path is xmeml version 4 with full file
definitions on every clipitem and explicit A/V link groups. Video and audio are
separate tracks so a J/L-cut is two clipitems with different in/out points.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4

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

    media, _, _ = require_timeline(state)
    timebase = media.timebase()
    duration = timeline_duration_frames(state)

    root = ET.Element("xmeml", {"version": "4"})
    sequence = ET.SubElement(
        root,
        "sequence",
        {"id": "sequence-1", "explodedTracks": "true"},
    )
    ET.SubElement(sequence, "uuid").text = str(uuid4())
    ET.SubElement(sequence, "name").text = "VideoFlow"
    ET.SubElement(sequence, "duration").text = str(duration)
    _append_rate(sequence, media)
    _append_sequence_timecode(sequence, media)

    media_element = ET.SubElement(sequence, "media")
    video_element = ET.SubElement(media_element, "video")
    format_element = ET.SubElement(video_element, "format")
    characteristics = ET.SubElement(format_element, "samplecharacteristics")
    _append_video_characteristics(characteristics, media)

    video_items: list[ET.Element] = []
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
        _append_file(item, media, file_id=f"file-video-{index + 1}")
        _append_motion(item, clip)
        video_items.append(item)

    audio_element = ET.SubElement(media_element, "audio")
    _append_audio_format(audio_element, media)
    audio_items: list[ET.Element] = []
    audio_track = ET.SubElement(audio_element, "track")
    for index, clip in enumerate(state.audio_segments):
        audio_start = timebase.sample_to_frame(clip.timeline_in_sample, Rounding.NEAREST)
        audio_end = timebase.sample_to_frame(clip.timeline_out_sample, Rounding.CEIL)
        fade_in_frames = timebase.sample_to_frame(clip.fade_in_samples, Rounding.CEIL)
        fade_out_frames = timebase.sample_to_frame(clip.fade_out_samples, Rounding.CEIL)
        if fade_in_frames > 0:
            _append_audio_fade(
                audio_track,
                media,
                start=audio_start,
                end=min(audio_end, audio_start + fade_in_frames),
                alignment="start-black",
                number=index + 1,
            )
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
        _append_file(item, media, file_id=f"file-audio-{index + 1}")
        audio_items.append(item)
        if fade_out_frames > 0:
            _append_audio_fade(
                audio_track,
                media,
                start=max(audio_start, audio_end - fade_out_frames),
                end=audio_end,
                alignment="end-black",
                number=index + 1,
            )

    for index, (video_item, audio_item) in enumerate(
        zip(video_items, audio_items, strict=True), start=1
    ):
        video_id = f"clipitem-{index}"
        audio_id = f"audioitem-{index}"
        _append_link(video_item, video_id, "video", index)
        _append_link(video_item, audio_id, "audio", index)
        _append_link(audio_item, video_id, "video", index)
        _append_link(audio_item, audio_id, "audio", index)

    return write_text(output_path, xml_document(root, "xmeml"))


def _append_sequence_timecode(sequence: ET.Element, media: MediaInfo) -> None:
    timecode = ET.SubElement(sequence, "timecode")
    _append_rate(timecode, media)
    ET.SubElement(timecode, "frame").text = "0"
    ET.SubElement(timecode, "displayformat").text = "NDF"


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


def _append_motion(parent: ET.Element, clip: VideoSegment) -> None:
    transform = clip.transform
    if transform.scale == 1.0 and not transform.keyframes:
        return
    filter_element = ET.SubElement(parent, "filter")
    effect = ET.SubElement(filter_element, "effect")
    ET.SubElement(effect, "name").text = "Basic Motion"
    ET.SubElement(effect, "effectid").text = "basicmotion"
    ET.SubElement(effect, "effectcategory").text = "motion"
    ET.SubElement(effect, "effecttype").text = "motion"
    ET.SubElement(effect, "mediatype").text = "video"
    parameter = ET.SubElement(effect, "parameter")
    ET.SubElement(parameter, "parameterid").text = "scale"
    ET.SubElement(parameter, "name").text = "Scale"
    ET.SubElement(parameter, "value").text = str(round(transform.scale * 100))
    if transform.keyframes:
        duration = max(1, clip.timeline_out_frame - clip.timeline_in_frame)
        for keyframe in transform.keyframes:
            key = ET.SubElement(parameter, "keyframe")
            ET.SubElement(key, "when").text = str(round(keyframe.at * duration))
            ET.SubElement(key, "value").text = str(round(keyframe.scale * 100))


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
