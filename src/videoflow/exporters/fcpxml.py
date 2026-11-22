"""FCPXML for DaVinci Resolve.

J/L-cuts use ``audioStart`` and ``audioDuration`` on the composite asset-clip,
which is the FCPXML mechanism for offsetting audio from its own picture.
Audio fade edges use keyframed ``adjust-volume`` ramps. Progressive zooms use a
keyframed ``adjust-transform`` scale parameter.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal

from videoflow.domain.state import ProjectState
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

from .fcpxml_extras import _append_extras
from .fcpxml_helpers import (
    _append_audio_fade,
    _append_transform,
    _audio_rate_label,
    _rate_label,
    _seconds,
    _tc_format,
)

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

    _append_extras(
        sequence=sequence,
        spine=spine,
        extras=extras,
        media=media,
        timebase=timebase,
        duration_frames=duration_frames,
        broll_assets=broll_assets,
        music_assets=music_assets,
    )
    return write_text(output_path, xml_document(root, "fcpxml"))














