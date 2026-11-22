"""XMEML helper: top-level timeline."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4

from videoflow.domain.state import ProjectState
from videoflow.domain.timebase import Rounding
from videoflow.exporters.common import (
    require_timeline,
    timeline_duration_frames,
    write_text,
    xml_document,
)
from videoflow.exporters.extras import EMPTY, NleExtras

from .common import (
    _append_audio_format,
    _append_color_filter,
    _append_file,
    _append_link,
    _append_rate,
    _append_sequence_timecode,
    _append_video_characteristics,
)
from .motion import _append_audio_fade, _append_motion, _append_video_transition
from .tracks import (
    _append_audio_stem,
    _append_broll_track,
    _append_caption_track,
    _append_marker,
    _append_music,
    _append_quarantine,
    _append_title,
)


def export_xmeml(
    state: ProjectState,
    output_path: Path,
    *,
    extras: NleExtras = EMPTY,
) -> Path:
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
        clip_media = state.video_media(clip) or media
        item = ET.SubElement(video_track, "clipitem", {"id": f"clipitem-{index + 1}"})
        ET.SubElement(item, "name").text = clip.clip_id
        ET.SubElement(item, "duration").text = str(clip_media.duration_frames)
        _append_rate(item, clip_media)
        ET.SubElement(item, "start").text = str(clip.timeline_in_frame)
        ET.SubElement(item, "end").text = str(clip.timeline_out_frame)
        ET.SubElement(item, "in").text = str(clip.source_in_frame)
        ET.SubElement(item, "out").text = str(clip.source_out_frame)
        _append_file(item, clip_media, file_id=f"file-video-{index + 1}")
        _append_motion(item, clip, media)
        if extras.color_filters:
            _append_color_filter(item)
        for adjustment in extras.adjustments:
            clip_start = clip.timeline_in_frame / (media.fps_num / media.fps_den)
            clip_end = clip.timeline_out_frame / (media.fps_num / media.fps_den)
            if clip_end <= adjustment.start_sec or clip_start >= adjustment.end_sec:
                continue
            filter_element = ET.SubElement(item, "filter")
            effect = ET.SubElement(filter_element, "effect")
            ET.SubElement(effect, "name").text = "Adjustment Layer"
            ET.SubElement(effect, "effectid").text = "adjustmentLayer"
            ET.SubElement(effect, "effectcategory").text = "video"
            ET.SubElement(effect, "effecttype").text = "filter"
            ET.SubElement(effect, "mediatype").text = "video"
            if adjustment.lut_path:
                parameter = ET.SubElement(effect, "parameter")
                ET.SubElement(parameter, "parameterid").text = "lut"
                ET.SubElement(parameter, "name").text = "LUT"
                ET.SubElement(parameter, "value").text = adjustment.lut_path
            if adjustment.grain_amount > 0:
                parameter = ET.SubElement(effect, "parameter")
                ET.SubElement(parameter, "parameterid").text = "grain"
                ET.SubElement(parameter, "name").text = "Grain"
                ET.SubElement(
                    parameter, "value"
                ).text = f"{adjustment.grain_amount:.3f}@{adjustment.grain_fps:.1f}fps"
        if clip.transition_out is not None:
            _append_video_transition(
                video_track,
                clip,
                media,
                number=index + 1,
            )
        video_items.append(item)

    audio_element = ET.SubElement(media_element, "audio")
    _append_audio_format(audio_element, media)
    audio_items: list[ET.Element] = []
    audio_track = ET.SubElement(audio_element, "track")
    for index, clip in enumerate(state.audio_segments):
        clip_media = state.audio_media(clip) or media
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
        ET.SubElement(item, "duration").text = str(clip_media.duration_frames)
        _append_rate(item, clip_media)
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
        _append_file(item, clip_media, file_id=f"file-audio-{index + 1}")
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

    _append_quarantine(video_element, sequence, state, media)
    if extras.broll:
        _append_broll_track(video_element, extras, media, max_z=39)
    for index, title in enumerate(extras.titles, start=1):
        _append_title(video_track, title, media, number=index)
    if extras.captions:
        _append_caption_track(video_element, extras, media)
    if extras.broll:
        _append_broll_track(video_element, extras, media, min_z=40)
    if extras.audio_stem:
        _append_audio_stem(audio_element, extras, media, duration)
    for index, entry in enumerate(extras.music, start=1):
        _append_music(audio_element, entry, media, number=index)
    for marker in extras.markers:
        _append_marker(sequence, marker, media.fps_num / media.fps_den)

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
