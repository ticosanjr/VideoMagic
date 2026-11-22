"""FCPXML titles, captions, B-roll, music and markers."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from videoflow.domain.timebase import format_rational_time
from videoflow.exporters.extras import NleExtras

from .fcpxml_helpers import _append_music_volume, _seconds


def _append_extras(
    *,
    sequence: ET.Element,
    spine: ET.Element,
    extras: NleExtras,
    media: Any,
    timebase: Any,
    duration_frames: int,
    broll_assets: dict[str, str],
    music_assets: dict[str, str],
) -> None:
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
