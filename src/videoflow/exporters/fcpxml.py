"""FCPXML for DaVinci Resolve.

J/L-cuts use ``audioStart`` and ``audioDuration`` on the composite asset-clip,
which is the FCPXML mechanism for offsetting audio from its own picture.
Audio fade edges use keyframed ``adjust-volume`` ramps. Progressive zooms use a
keyframed ``adjust-transform`` scale parameter.
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
from videoflow.exporters.extras import EMPTY, NleExtras

Dialect = Literal["1.9", "1.10"]


def export_fcpxml(
    state: ProjectState,
    output_path: Path,
    *,
    dialect: Dialect = "1.10",
    extras: NleExtras = EMPTY,
) -> Path:
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
    source_assets: dict[str, str] = {}
    ordered_sources = []
    if state.primary_source_id and state.primary_source_id in state.sources:
        ordered_sources.append(state.primary_source_id)
    ordered_sources.extend(
        source_id for source_id in state.sources if source_id not in ordered_sources
    )
    if not ordered_sources:
        ordered_sources = [state.primary_source_id or "primary"]
    for index, source_id in enumerate(ordered_sources, start=1):
        source_media = state.sources.get(source_id) or media
        asset_id = f"a{index}"
        source_assets[source_id] = asset_id
        asset = ET.SubElement(
            resources,
            "asset",
            {
                "id": asset_id,
                "name": Path(source_media.source_path).name,
                "start": "0s",
                "duration": format_rational_time(
                    timebase.frames_to_seconds(source_media.duration_frames)
                ),
                "hasVideo": "1",
                "videoSources": "1",
                "hasAudio": "1",
                "format": "r1",
                "audioSources": "1",
                "audioChannels": "1",
                "audioRate": str(source_media.audio_sample_rate),
            },
        )
        ET.SubElement(
            asset,
            "media-rep",
            {"kind": "original-media", "src": file_uri(source_media.source_path)},
        )

    if extras.titles or extras.captions:
        ET.SubElement(
            resources,
            "effect",
            {
                "id": "r2",
                "name": "Basic Title",
                "uid": (
                    ".../Titles.localized/Bumper:Opener.localized/"
                    "Basic Title.localized/Basic Title.moti"
                ),
            },
        )
    if extras.color_filters:
        ET.SubElement(
            resources,
            "effect",
            {"id": "r3", "name": "Color Correction", "uid": ".../Color Correction"},
        )
    if extras.adjustments:
        ET.SubElement(
            resources,
            "effect",
            {"id": "r4", "name": "Adjustment Layer", "uid": ".../Adjustment Layer"},
        )
    broll_assets: dict[str, str] = {}
    for entry in extras.broll:
        if entry.path in broll_assets:
            continue
        asset_id = f"b{len(broll_assets) + 1}"
        broll_assets[entry.path] = asset_id
        bro = ET.SubElement(
            resources,
            "asset",
            {
                "id": asset_id,
                "name": Path(entry.path).name,
                "start": "0s",
                "duration": format_rational_time(timebase.frames_to_seconds(media.duration_frames)),
                "hasVideo": "1",
                "videoSources": "1",
                "format": "r1",
            },
        )
        ET.SubElement(
            bro,
            "media-rep",
            {"kind": "original-media", "src": file_uri(entry.path)},
        )

    if extras.audio_stem:
        stem = ET.SubElement(
            resources,
            "asset",
            {
                "id": "stem1",
                "name": Path(extras.audio_stem).name,
                "start": "0s",
                "duration": format_rational_time(timebase.frames_to_seconds(duration_frames)),
                "hasAudio": "1",
                "format": "r1",
                "audioSources": "1",
                "audioChannels": "1",
                "audioRate": str(media.audio_sample_rate),
            },
        )
        ET.SubElement(
            stem,
            "media-rep",
            {"kind": "original-media", "src": file_uri(extras.audio_stem)},
        )
    music_assets: dict[str, str] = {}
    for entry in extras.music:
        if entry.path in music_assets:
            continue
        asset_id = f"m{len(music_assets) + 1}"
        music_assets[entry.path] = asset_id
        music = ET.SubElement(
            resources,
            "asset",
            {
                "id": asset_id,
                "name": Path(entry.path).name,
                "start": "0s",
                "duration": format_rational_time(_seconds(entry.duration_sec)),
                "hasAudio": "1",
                "format": "r1",
                "audioSources": "1",
                "audioChannels": "1",
                "audioRate": str(media.audio_sample_rate),
            },
        )
        ET.SubElement(
            music,
            "media-rep",
            {"kind": "original-media", "src": file_uri(entry.path)},
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
        clip_source = clip.source_id or state.primary_source_id or "primary"
        element = ET.SubElement(
            spine,
            "asset-clip",
            {
                "ref": source_assets.get(clip_source, "a1"),
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
        if extras.color_filters:
            ET.SubElement(element, "filter-video", {"ref": "r3", "name": "Color Correction"})
        for adjustment in extras.adjustments:
            clip_start = timebase.frames_to_seconds(clip.timeline_in_frame)
            clip_end = timebase.frames_to_seconds(clip.timeline_out_frame)
            if clip_end <= adjustment.start_sec or clip_start >= adjustment.end_sec:
                continue
            filter_element = ET.SubElement(
                element, "filter-video", {"ref": "r4", "name": "Adjustment Layer"}
            )
            if adjustment.lut_path:
                ET.SubElement(
                    filter_element, "param", {"name": "LUT", "value": adjustment.lut_path}
                )
            if adjustment.grain_amount > 0:
                ET.SubElement(
                    filter_element,
                    "param",
                    {
                        "name": "Grain",
                        "value": f"{adjustment.grain_amount:.3f}@{adjustment.grain_fps:.1f}fps",
                    },
                )
        if clip.transition_out is not None:
            ET.SubElement(
                spine,
                "transition",
                {
                    "name": (
                        "Cross Dissolve"
                        if clip.transition_out.type == "crossfade"
                        else "Fade to Black"
                    ),
                    "duration": format_rational_time(
                        timebase.frames_to_seconds(clip.transition_out.duration_frames)
                    ),
                },
            )

    quarantine_colors = {
        "retake": "red",
        "noise": "orange",
        "manual": "yellow",
        "silence": "gray",
    }
    for inactive in state.inactive_segments:
        clip = inactive.video
        source_id = clip.source_id or state.primary_source_id or "primary"
        start_sec = timebase.frames_to_seconds(clip.source_in_frame)
        duration_sec = timebase.frames_to_seconds(
            clip.source_out_frame - clip.source_in_frame
        )
        element = ET.SubElement(
            spine,
            "asset-clip",
            {
                "ref": source_assets.get(source_id, "a1"),
                "lane": "1",
                "name": f"Quarantine V2/A2 {inactive.clip_id} ({inactive.reason})",
                "offset": format_rational_time(start_sec),
                "start": format_rational_time(start_sec),
                "duration": format_rational_time(duration_sec),
                "audioStart": format_rational_time(
                    timebase.samples_to_seconds(inactive.audio.source_in_sample)
                ),
                "audioDuration": format_rational_time(
                    timebase.samples_to_seconds(
                        inactive.audio.source_out_sample
                        - inactive.audio.source_in_sample
                    )
                ),
                "srcEnable": "all",
                "enabled": "0",
                "audioRole": "dialogue",
            },
        )
        ET.SubElement(
            element,
            "marker",
            {
                "start": "0s",
                "duration": format_rational_time(duration_sec),
                "value": inactive.reason.upper(),
                "note": f"Quarantine V2/A2: {inactive.reason}",
                "color": quarantine_colors.get(inactive.reason, "gray"),
            },
        )

    for entry in extras.broll:
        asset_id = broll_assets.get(entry.path)
        if asset_id is None:
            continue
        lane = 2
        if entry.z >= 50:
            lane = 7
        elif entry.z >= 40:
            lane = 5
        elif entry.z >= 30:
            lane = 4
        elif entry.z >= 20:
            lane = 3
        clip = ET.SubElement(
            spine,
            "asset-clip",
            {
                "ref": asset_id,
                "lane": str(lane),
                "name": entry.name or Path(entry.path).stem,
                "offset": format_rational_time(entry.start_sec),
                "start": "0s",
                "duration": format_rational_time(entry.duration_sec),
                "srcEnable": "video",
                "videoRole": "B-roll",
            },
        )
        if entry.width and entry.height and entry.source_width and entry.source_height:
            center_x = entry.x + entry.width / 2
            center_y = entry.y + entry.height / 2
            position_x = round(center_x - media.width / 2, 3)
            position_y = round(media.height / 2 - center_y, 3)
            ET.SubElement(
                clip,
                "adjust-transform",
                {
                    "position": f"{position_x:g} {position_y:g}",
                    "scale": (
                        f"{entry.width / entry.source_width:.6f} "
                        f"{entry.height / entry.source_height:.6f}"
                    ),
                    "anchor": "0 0",
                },
            )

    for index, title in enumerate(extras.titles, start=1):
        element = ET.SubElement(
            spine,
            "title",
            {
                "ref": "r2",
                "lane": "3",
                "name": title.kind.replace("_", " ").title(),
                "offset": format_rational_time(title.start_sec),
                "duration": format_rational_time(max(0.1, title.end_sec - title.start_sec)),
            },
        )
        style_id = f"ts{index}"
        text = ET.SubElement(element, "text")
        ET.SubElement(text, "text-style", {"ref": style_id}).text = title.text
        definition = ET.SubElement(element, "text-style-def", {"id": style_id})
        ET.SubElement(
            definition,
            "text-style",
            {
                "font": "Helvetica",
                "fontSize": "48",
                "fontColor": "1 1 1 1",
                "alignment": "center",
            },
        )

    for index, caption in enumerate(extras.captions, start=1):
        element = ET.SubElement(
            spine,
            "title",
            {
                "ref": "r2",
                "lane": "6",
                "name": "Caption",
                "offset": format_rational_time(_seconds(caption.start_sec)),
                "duration": format_rational_time(
                    _seconds(max(0.1, caption.end_sec - caption.start_sec))
                ),
            },
        )
        style_id = f"cs{index}"
        text = ET.SubElement(element, "text")
        ET.SubElement(text, "text-style", {"ref": style_id}).text = caption.text
        definition = ET.SubElement(element, "text-style-def", {"id": style_id})
        ET.SubElement(
            definition,
            "text-style",
            {
                "font": "Helvetica",
                "fontSize": "42",
                "fontColor": "1 1 1 1",
                "alignment": "center",
            },
        )

    if extras.audio_stem:
        ET.SubElement(
            spine,
            "asset-clip",
            {
                "ref": "stem1",
                "lane": "4",
                "name": "Audio master",
                "offset": "0s",
                "start": "0s",
                "duration": format_rational_time(timebase.frames_to_seconds(duration_frames)),
                "srcEnable": "audio",
                "audioRole": "effects",
            },
        )

    for entry in extras.music:
        asset_id = music_assets.get(entry.path)
        if asset_id is None:
            continue
        element = ET.SubElement(
            spine,
            "asset-clip",
            {
                "ref": asset_id,
                "lane": "5",
                "name": Path(entry.path).stem,
                "offset": format_rational_time(_seconds(entry.start_sec)),
                "start": "0s",
                "duration": format_rational_time(_seconds(entry.duration_sec)),
                "srcEnable": "audio",
                "audioRole": "music",
            },
        )
        _append_music_volume(element, entry)

    for marker in extras.markers:
        ET.SubElement(
            sequence,
            "marker",
            {
                "start": format_rational_time(marker.start_sec),
                "duration": format_rational_time(max(0.0, marker.end_sec - marker.start_sec)),
                "value": marker.name,
                "note": marker.note,
            },
        )

    return write_text(output_path, xml_document(root, "fcpxml"))


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
