"""Kdenlive helper: filters, guides, captions and overlays."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .common import _property, _timecode, _transform_rect

_QUARANTINE_COLORS = {
    "retake": "#ef4444",
    "noise": "#f97316",
    "manual": "#eab308",
    "silence": "#9ca3af",
}


def _append_video_filter(
    entry: ET.Element,
    clip,
    media,
    duration_frames: int,
    *,
    previous_transition=None,
    index: int = 0,
    color: bool = False,
    fade_in: int | None = None,
    fade_out: int | None = None,
) -> None:
    if color:
        _append_color_filters(entry)
    transform = clip.transform
    if fade_in is None:
        fade_in = previous_transition.duration_frames if previous_transition is not None else 0
    if fade_out is None:
        fade_out = clip.transition_out.duration_frames if clip.transition_out is not None else 0
    fade_in = min(fade_in, max(0, duration_frames - 1))
    fade_out = min(fade_out, max(0, duration_frames - 1))
    keyframes: dict[int, tuple[int, int, int, int, float]] = {}
    if transform.keyframes:
        for keyframe in transform.keyframes:
            frame = round(keyframe.at * max(1, duration_frames - 1))
            keyframes[frame] = _transform_rect(
                media,
                keyframe.scale,
                keyframe.pos_x,
                keyframe.pos_y,
                transform.anchor,
                transform.pan_direction,
                1.0,
            )
    elif (
        transform.scale != 1.0
        or transform.pos_x != 0.0
        or transform.pos_y != 0.0
        or transform.type != "none"
        or transform.pan_direction != "none"
    ):
        keyframes[0] = _transform_rect(
            media,
            transform.scale,
            transform.pos_x,
            transform.pos_y,
            transform.anchor,
            transform.pan_direction,
            1.0,
        )
    if fade_in > 0:
        base = keyframes.get(0) or _transform_rect(
            media,
            transform.scale,
            transform.pos_x,
            transform.pos_y,
            transform.anchor,
            transform.pan_direction,
            1.0,
        )
        keyframes[0] = (*base[:4], 0.0)
        keyframes[fade_in] = (*keyframes.get(fade_in, base)[:4], 1.0)
    if fade_out > 0:
        base = keyframes.get(0) or _transform_rect(
            media,
            transform.scale,
            transform.pos_x,
            transform.pos_y,
            transform.anchor,
            transform.pan_direction,
            1.0,
        )
        start = max(0, duration_frames - 1 - fade_out)
        keyframes[start] = (*keyframes.get(start, base)[:4], 1.0)
        keyframes[max(0, duration_frames - 1)] = (*base[:4], 0.0)
    if not keyframes:
        return
    ordered = [keyframes[frame] for frame in sorted(keyframes)]
    if len(ordered) == 1:
        geometry = " ".join(str(value) for value in ordered[0])
    else:
        geometry = ";".join(
            f"{frame}=" + " ".join(str(value) for value in values)
            for frame, values in sorted(keyframes.items())
        )
    filter_element = ET.SubElement(
        entry,
        "filter",
        {
            "id": f"filter-transform-{index}-{clip.clip_id}",
            "in": _timecode(0, media.fps_num, media.fps_den),
            "out": _timecode(max(0, duration_frames - 1), media.fps_num, media.fps_den),
        },
    )
    _property(filter_element, "mlt_service", "affine")
    _property(filter_element, "kdenlive_id", "affine")
    _property(filter_element, "transition.fill", "1")
    _property(filter_element, "transition.distort", "1")
    _property(filter_element, "transition.rect", geometry)
    _property(filter_element, "transition.geometry", geometry)

def _append_color_filters(entry: ET.Element) -> None:
    filter_element = ET.SubElement(entry, "filter")
    _property(filter_element, "mlt_service", "lift_gamma_gain")
    _property(filter_element, "lift_r", "0")
    _property(filter_element, "lift_g", "0")
    _property(filter_element, "lift_b", "0")
    _property(filter_element, "gamma_r", "1")
    _property(filter_element, "gamma_g", "1")
    _property(filter_element, "gamma_b", "1")
    _property(filter_element, "gain_r", "1")
    _property(filter_element, "gain_g", "1")
    _property(filter_element, "gain_b", "1")

def _append_guides(main_bin: ET.Element, extras, media, state=None) -> None:
    guides = []
    if extras is not None:
        fps = media.fps_num / media.fps_den
        guides.extend(
            {
                "comment": marker.name
                if not marker.note
                else f"{marker.name}: {marker.note}",
                "pos": round(marker.start_sec * fps),
                "type": 0,
                "color": marker.color or "#38bdf8",
            }
            for marker in extras.markers
        )
    for inactive in getattr(state, "inactive_segments", None) or []:
        guides.append(
            {
                "comment": (
                    f"Quarantine V2/A2 {inactive.clip_id} ({inactive.reason})"
                ),
                "pos": int(inactive.video.source_in_frame),
                "type": 0,
                "color": _QUARANTINE_COLORS.get(inactive.reason, "#9ca3af"),
            }
        )
    if not guides:
        return
    import json

    guides.sort(key=lambda item: (item["pos"], item["comment"]))
    _property(main_bin, "kdenlive:docproperties.guides", json.dumps(guides))

def _title_xml(title, width: int, height: int) -> str:
    text = title.text.replace("&", "&amp;").replace("<", "&lt;")
    size = 64 if title.kind == "title" else 40
    return (
        f'<kdenlivetitle duration="9999" LC_NUMERIC="C" width="{width}" '
        f'height="{height}" out="9998"><item type="QGraphicsTextItem" z-index="0">'
        '<position x="120" y="960"><transform>1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1'
        f'</transform></position><content font="Arial" font-size="{size}" '
        'font-weight="63" font-outline="3" font-pixel-size="'
        f'{size}" font-color="255,255,255,255" alignment="1">{text}</content>'
        "</item></kdenlivetitle>"
    )

def _append_stem_playlist(parent: ET.Element, extras, media, duration_frames: int) -> str:
    producer = ET.SubElement(parent, "producer", {"id": "audio_stem"})
    _property(producer, "resource", extras.audio_stem)
    _property(producer, "mlt_service", "avformat")
    _property(producer, "kdenlive:duration", str(duration_frames))
    _property(producer, "kdenlive:clipname", "Audio master")
    _property(producer, "hide", "video")
    playlist = ET.SubElement(parent, "playlist", {"id": "playlist5"})
    ET.SubElement(
        playlist,
        "entry",
        {
            "producer": "audio_stem",
            "in": "00:00:00.000",
            "out": _timecode(duration_frames - 1, media.fps_num, media.fps_den),
        },
    )
    return "playlist5"

def _append_music_playlist(parent: ET.Element, extras, media, duration_frames: int) -> str:
    playlist = ET.SubElement(parent, "playlist", {"id": "playlist_music"})
    cursor = 0
    for index, entry in enumerate(extras.music):
        producer_id = f"music{index}"
        producer = ET.SubElement(parent, "producer", {"id": producer_id})
        _property(producer, "resource", entry.path)
        _property(producer, "mlt_service", "avformat")
        _property(producer, "hide", "video")
        _property(producer, "kdenlive:clipname", Path(entry.path).stem)
        start = round(entry.start_sec * media.fps_num / media.fps_den)
        length = max(1, round(entry.duration_sec * media.fps_num / media.fps_den))
        if start > cursor:
            ET.SubElement(playlist, "blank", {"length": str(start - cursor)})
            cursor = start
        item = ET.SubElement(
            playlist,
            "entry",
            {
                "producer": producer_id,
                "in": "00:00:00.000",
                "out": _timecode(length - 1, media.fps_num, media.fps_den),
            },
        )
        _append_music_volume(item, entry, media, length)
        cursor += length
    if cursor < duration_frames:
        ET.SubElement(playlist, "blank", {"length": str(duration_frames - cursor)})
    return "playlist_music"

def _append_music_volume(entry_element: ET.Element, entry, media, length: int) -> None:
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
    points.append((max(0, length - 1), entry.gain_db))
    seen: set[int] = set()
    ordered: list[str] = []
    for frame, value in sorted(points):
        if frame in seen:
            continue
        seen.add(frame)
        ordered.append(f"{frame}={value:g}")
    filter_element = ET.SubElement(
        entry_element,
        "filter",
        {"id": f"filter-music-{id(entry_element)}"},
    )
    _property(filter_element, "window", "75")
    _property(filter_element, "max_gain", "20dB")
    _property(filter_element, "mlt_service", "volume")
    _property(filter_element, "kdenlive_id", "volume")
    _property(filter_element, "level", ";".join(ordered))

def _append_captions_playlist(parent: ET.Element, extras, media, duration_frames: int) -> str:
    playlist = ET.SubElement(parent, "playlist", {"id": "playlist_captions"})
    cursor = 0
    for index, caption in enumerate(extras.captions):
        producer_id = f"caption{index}"
        start = round(caption.start_sec * media.fps_num / media.fps_den)
        length = max(
            1,
            round((caption.end_sec - caption.start_sec) * media.fps_num / media.fps_den),
        )
        producer = ET.SubElement(parent, "producer", {"id": producer_id})
        _property(producer, "mlt_service", "kdenlivetitle")
        _property(producer, "kdenlive:duration", str(length))
        _property(producer, "kdenlive:clipname", "Caption")
        _property(producer, "xml", _title_xml(caption, media.width, media.height))
        if start > cursor:
            ET.SubElement(playlist, "blank", {"length": str(start - cursor)})
            cursor = start
        ET.SubElement(
            playlist,
            "entry",
            {
                "producer": producer_id,
                "in": "00:00:00.000",
                "out": _timecode(length - 1, media.fps_num, media.fps_den),
            },
        )
        cursor += length
    if cursor < duration_frames:
        ET.SubElement(playlist, "blank", {"length": str(duration_frames - cursor)})
    return "playlist_captions"

def _append_broll_geometry(producer: ET.Element, entry, media) -> None:
    if not (entry.width and entry.height):
        return
    geometry = ET.SubElement(producer, "filter", {"id": f"{producer.get('id')}-geometry"})
    _property(geometry, "mlt_service", "qtblend")
    _property(geometry, "rect", f"{entry.x} {entry.y} {entry.width} {entry.height} 1")
    _property(geometry, "compositing", "0")
    _property(geometry, "distort", "0")
    if entry.opacity < 1:
        _property(geometry, "opacity", f"{entry.opacity:.3f}")

def _append_overlay_playlist(parent: ET.Element, extras, media, duration_frames: int) -> str:
    entries: list[tuple[str, int, int]] = []
    for index, title in enumerate(extras.titles):
        producer_id = f"title{index}"
        start = round(title.start_sec * media.fps_num / media.fps_den)
        length = max(1, round((title.end_sec - title.start_sec) * media.fps_num / media.fps_den))
        producer = ET.SubElement(parent, "producer", {"id": producer_id})
        _property(producer, "mlt_service", "kdenlivetitle")
        _property(producer, "kdenlive:duration", str(length))
        _property(producer, "kdenlive:clipname", title.kind.replace("_", " ").title())
        _property(producer, "xml", _title_xml(title, media.width, media.height))
        entries.append((producer_id, start, length))
    for index, entry in enumerate(extras.broll):
        producer_id = f"broll{index}"
        start = round(entry.start_sec * media.fps_num / media.fps_den)
        length = max(1, round(entry.duration_sec * media.fps_num / media.fps_den))
        producer = ET.SubElement(parent, "producer", {"id": producer_id})
        _property(producer, "resource", entry.path)
        _property(
            producer,
            "mlt_service",
            "qimage" if getattr(entry, "kind", "video") == "image" else "avformat",
        )
        _property(producer, "kdenlive:duration", str(length))
        if getattr(entry, "kind", "video") == "image":
            _property(producer, "ttl", str(max(1, length)))
            _property(producer, "length", str(max(1, length)))
            _property(producer, "eof", "continue")
        _property(producer, "kdenlive:clipname", entry.name or "B-roll")
        _append_broll_geometry(producer, entry, media)
        entries.append((producer_id, start, length))
    if not entries:
        return ""
    playlist = ET.SubElement(parent, "playlist", {"id": "playlist4"})
    cursor = 0
    for producer_id, start, length in sorted(entries, key=lambda item: item[1]):
        if start > cursor:
            ET.SubElement(playlist, "blank", {"length": str(start - cursor)})
            cursor = start
        ET.SubElement(
            playlist,
            "entry",
            {
                "producer": producer_id,
                "in": "00:00:00.000",
                "out": _timecode(length - 1, media.fps_num, media.fps_den),
            },
        )
        cursor += length
    if cursor < duration_frames:
        ET.SubElement(playlist, "blank", {"length": str(duration_frames - cursor)})
    return "playlist4"
