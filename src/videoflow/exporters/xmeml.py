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
from videoflow.exporters.extras import EMPTY, NleExtras


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


def _append_sequence_timecode(sequence: ET.Element, media: MediaInfo) -> None:
    timecode = ET.SubElement(sequence, "timecode")
    _append_rate(timecode, media)
    ET.SubElement(timecode, "frame").text = "0"
    ET.SubElement(timecode, "displayformat").text = "NDF"


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


def _append_music(audio_element: ET.Element, entry, media: MediaInfo, *, number: int) -> None:
    """Add a music track with a ducking level envelope."""

    track = ET.SubElement(audio_element, "track")
    start = round(entry.start_sec * media.fps_num / media.fps_den)
    length = max(1, round(entry.duration_sec * media.fps_num / media.fps_den))
    item = ET.SubElement(track, "clipitem", {"id": f"music-{number}"})
    ET.SubElement(item, "name").text = Path(entry.path).stem
    ET.SubElement(item, "duration").text = str(length)
    _append_rate(item, media)
    ET.SubElement(item, "start").text = str(start)
    ET.SubElement(item, "end").text = str(start + length)
    ET.SubElement(item, "in").text = "0"
    ET.SubElement(item, "out").text = str(length)
    source_track = ET.SubElement(item, "sourcetrack")
    ET.SubElement(source_track, "mediatype").text = "audio"
    ET.SubElement(source_track, "trackindex").text = "1"
    file_element = ET.SubElement(item, "file", {"id": f"file-music-{number}"})
    ET.SubElement(file_element, "name").text = Path(entry.path).name
    ET.SubElement(file_element, "pathurl").text = _premiere_path_url(entry.path)
    _append_rate(file_element, media)
    ET.SubElement(file_element, "duration").text = str(length)

    points: list[tuple[int, float]] = [(0, entry.gain_db)]
    fps = media.fps_num / media.fps_den
    for duck_start, duck_end, level in entry.duck_ranges:
        local_start = max(0.0, duck_start - entry.start_sec)
        local_end = min(entry.duration_sec, duck_end - entry.start_sec)
        if local_end <= local_start:
            continue
        ducked = entry.gain_db + level
        points.extend(
            [
                (round(local_start * fps), entry.gain_db),
                (round(min(local_end, local_start + 0.15) * fps), ducked),
                (round(max(local_start, local_end - 0.15) * fps), ducked),
                (round(local_end * fps), entry.gain_db),
            ]
        )
    points.append((length, entry.gain_db))
    filter_element = ET.SubElement(item, "filter")
    effect = ET.SubElement(filter_element, "effect")
    ET.SubElement(effect, "name").text = "Audio Levels"
    ET.SubElement(effect, "effectid").text = "audiolevels"
    ET.SubElement(effect, "effectcategory").text = "audio"
    ET.SubElement(effect, "effecttype").text = "filter"
    ET.SubElement(effect, "mediatype").text = "audio"
    parameter = ET.SubElement(effect, "parameter")
    ET.SubElement(parameter, "parameterid").text = "level"
    ET.SubElement(parameter, "name").text = "Level"
    ET.SubElement(parameter, "value").text = f"{entry.gain_db:g}"
    seen: set[int] = set()
    for when, value in sorted(points):
        if when in seen:
            continue
        seen.add(when)
        keyframe = ET.SubElement(parameter, "keyframe")
        ET.SubElement(keyframe, "when").text = str(when)
        ET.SubElement(keyframe, "value").text = f"{value:g}"


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


_QUARANTINE_COLORS = {
    "retake": "#ef4444",
    "noise": "#f97316",
    "manual": "#eab308",
    "silence": "#9ca3af",
}


def _append_quarantine(
    video_element: ET.Element,
    sequence: ET.Element,
    state: ProjectState,
    media: MediaInfo,
) -> None:
    """Export inactive/removed clips on a disabled V2/A2 track plus markers."""

    segments = getattr(state, "inactive_segments", None) or []
    if not segments:
        return
    track = ET.SubElement(video_element, "track")
    ET.SubElement(track, "enabled").text = "FALSE"
    ET.SubElement(track, "locked").text = "TRUE"
    for index, inactive in enumerate(segments, start=1):
        clip = inactive.video
        clip_media = state.video_media(clip) or media
        start = int(clip.source_in_frame)
        duration = max(1, int(clip.source_out_frame - clip.source_in_frame))
        item = ET.SubElement(
            track,
            "clipitem",
            {"id": f"quarantine-{index}"},
        )
        ET.SubElement(item, "name").text = (
            f"Quarantine V2/A2 {inactive.clip_id} ({inactive.reason})"
        )
        ET.SubElement(item, "enabled").text = "FALSE"
        ET.SubElement(item, "duration").text = str(clip_media.duration_frames)
        _append_rate(item, clip_media)
        ET.SubElement(item, "start").text = str(start)
        ET.SubElement(item, "end").text = str(start + duration)
        ET.SubElement(item, "in").text = str(start)
        ET.SubElement(item, "out").text = str(start + duration)
        _append_file(item, clip_media, file_id=f"file-quarantine-{index}")

        marker = ET.SubElement(sequence, "marker")
        ET.SubElement(marker, "name").text = "Quarantine V2/A2"
        ET.SubElement(marker, "comment").text = (
            f"{inactive.clip_id}: {inactive.reason}"
        )
        ET.SubElement(marker, "in").text = str(start)
        ET.SubElement(marker, "out").text = str(start + duration)


def _append_marker(sequence: ET.Element, marker, fps: float) -> None:
    element = ET.SubElement(sequence, "marker")
    ET.SubElement(element, "name").text = marker.name
    ET.SubElement(element, "comment").text = marker.note
    start = round(marker.start_sec * fps)
    out = marker.end_sec if marker.end_sec > marker.start_sec else marker.start_sec
    ET.SubElement(element, "in").text = str(start)
    ET.SubElement(element, "out").text = str(round(out * fps))


def _append_title(video_track: ET.Element, title, media: MediaInfo, *, number: int) -> None:
    duration = max(1, round((title.end_sec - title.start_sec) * (media.fps_num / media.fps_den)))
    item = ET.SubElement(video_track, "generatoritem", {"id": f"title-{number}"})
    ET.SubElement(item, "name").text = title.kind.replace("_", " ").title()
    ET.SubElement(item, "duration").text = str(duration)
    _append_rate(item, media)
    ET.SubElement(item, "start").text = str(round(title.start_sec * media.fps_num / media.fps_den))
    ET.SubElement(item, "end").text = str(round(title.end_sec * media.fps_num / media.fps_den))
    ET.SubElement(item, "in").text = "0"
    ET.SubElement(item, "out").text = str(duration)
    effect = ET.SubElement(item, "effect")
    ET.SubElement(effect, "name").text = "Text"
    ET.SubElement(effect, "effectid").text = "Text"
    ET.SubElement(effect, "effectcategory").text = "Text"
    ET.SubElement(effect, "effecttype").text = "generator"
    ET.SubElement(effect, "mediatype").text = "video"
    parameter = ET.SubElement(effect, "parameter")
    ET.SubElement(parameter, "parameterid").text = "str"
    ET.SubElement(parameter, "name").text = "Text"
    ET.SubElement(parameter, "value").text = title.text


def _append_caption_track(
    video_element: ET.Element,
    extras: NleExtras,
    media: MediaInfo,
) -> None:
    track = ET.SubElement(video_element, "track")
    for index, caption in enumerate(extras.captions, start=1):
        duration = max(
            1, round((caption.end_sec - caption.start_sec) * (media.fps_num / media.fps_den))
        )
        item = ET.SubElement(track, "generatoritem", {"id": f"caption-{index}"})
        ET.SubElement(item, "name").text = "Caption"
        ET.SubElement(item, "duration").text = str(duration)
        _append_rate(item, media)
        ET.SubElement(item, "start").text = str(
            round(caption.start_sec * media.fps_num / media.fps_den)
        )
        ET.SubElement(item, "end").text = str(
            round(caption.end_sec * media.fps_num / media.fps_den)
        )
        ET.SubElement(item, "in").text = "0"
        ET.SubElement(item, "out").text = str(duration)
        effect = ET.SubElement(item, "effect")
        ET.SubElement(effect, "name").text = "Text"
        ET.SubElement(effect, "effectid").text = "Text"
        ET.SubElement(effect, "effectcategory").text = "Text"
        ET.SubElement(effect, "effecttype").text = "generator"
        ET.SubElement(effect, "mediatype").text = "video"
        parameter = ET.SubElement(effect, "parameter")
        ET.SubElement(parameter, "parameterid").text = "str"
        ET.SubElement(parameter, "name").text = "Text"
        ET.SubElement(parameter, "value").text = caption.text


def _append_broll_track(
    video_element: ET.Element,
    extras: NleExtras,
    media: MediaInfo,
    *,
    min_z: int | None = None,
    max_z: int | None = None,
) -> None:
    entries = [
        entry
        for entry in extras.broll
        if (min_z is None or entry.z >= min_z)
        and (max_z is None or entry.z <= max_z)
    ]
    grouped: dict[int, list] = {}
    for entry in entries:
        lane = 2
        if entry.z >= 50:
            lane = 7
        elif entry.z >= 40:
            lane = 5
        elif entry.z >= 30:
            lane = 4
        elif entry.z >= 20:
            lane = 3
        grouped.setdefault(lane, []).append(entry)
    for lane in sorted(grouped):
        track = ET.SubElement(video_element, "track")
        ET.SubElement(track, "name").text = f"Overlay z{lane}"
        for index, entry in enumerate(grouped[lane], start=1):
            start = round(entry.start_sec * media.fps_num / media.fps_den)
            end = round((entry.start_sec + entry.duration_sec) * media.fps_num / media.fps_den)
            item = ET.SubElement(track, "clipitem", {"id": f"broll-{lane}-{index}"})
            ET.SubElement(item, "name").text = entry.name or Path(entry.path).stem
            ET.SubElement(item, "duration").text = str(max(1, end - start))
            _append_rate(item, media)
            ET.SubElement(item, "start").text = str(start)
            ET.SubElement(item, "end").text = str(end)
            ET.SubElement(item, "in").text = "0"
            ET.SubElement(item, "out").text = str(max(1, end - start))
            if entry.kind == "image":
                ET.SubElement(item, "stillframe").text = "TRUE"
            file_element = ET.SubElement(item, "file", {"id": f"file-broll-{lane}-{index}"})
            ET.SubElement(file_element, "name").text = Path(entry.path).name
            ET.SubElement(file_element, "pathurl").text = _premiere_path_url(entry.path)
            _append_rate(file_element, media)
            ET.SubElement(file_element, "duration").text = str(max(1, end - start))
            _append_basic_motion(item, entry, media)


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


def _append_audio_stem(
    audio_element: ET.Element, extras: NleExtras, media: MediaInfo, duration: int
) -> None:
    track = ET.SubElement(audio_element, "track")
    item = ET.SubElement(track, "clipitem", {"id": "audio-stem"})
    ET.SubElement(item, "name").text = "Audio master"
    ET.SubElement(item, "duration").text = str(duration)
    _append_rate(item, media)
    ET.SubElement(item, "start").text = "0"
    ET.SubElement(item, "end").text = str(duration)
    ET.SubElement(item, "in").text = "0"
    ET.SubElement(item, "out").text = str(duration)
    source_track = ET.SubElement(item, "sourcetrack")
    ET.SubElement(source_track, "mediatype").text = "audio"
    ET.SubElement(source_track, "trackindex").text = "1"
    file_element = ET.SubElement(item, "file", {"id": "file-audio-stem"})
    ET.SubElement(file_element, "name").text = Path(extras.audio_stem).name
    ET.SubElement(file_element, "pathurl").text = _premiere_path_url(extras.audio_stem)
    _append_rate(file_element, media)
    ET.SubElement(file_element, "duration").text = str(duration)
