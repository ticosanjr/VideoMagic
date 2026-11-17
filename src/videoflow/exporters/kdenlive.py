"""Native Kdenlive/MLT XML for Kdenlive 23.04 and newer.

Kdenlive's own project format is an MLT XML document. It is more reliable than
asking Kdenlive to import an OTIO file because the timeline, tracks, and bin all
use the same MLT object model Kdenlive writes itself.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from math import gcd
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from videoflow.domain.state import ProjectState
from videoflow.domain.timebase import Rounding
from videoflow.exporters.common import (
    require_timeline,
    timeline_duration_frames,
    timeline_duration_samples,
    write_text,
)


def export_kdenlive(
    state: ProjectState,
    output_path: Path,
    *,
    extras=None,
) -> Path:
    """Write a native ``.kdenlive`` MLT XML project."""

    media, _, _ = require_timeline(state)
    timebase = media.timebase()
    video_frames = timeline_duration_frames(state)
    audio_frames = timebase.sample_to_frame(timeline_duration_samples(state), Rounding.CEIL)
    duration_frames = max(video_frames, audio_frames, 1)
    duration = _timecode(duration_frames, media.fps_num, media.fps_den)
    sequence_uuid = uuid5(NAMESPACE_URL, f"videoflow:{state.project_id}")
    sequence_id = f"{{{sequence_uuid}}}"
    document_id = str(sequence_uuid.int % 10_000_000_000_000)

    root = ET.Element(
        "mlt",
        {
            "LC_NUMERIC": "en_US.UTF-8",
            "producer": "main_bin",
            "version": "7.22.0",
        },
    )
    _append_profile(root, media)
    _append_black_track(root, duration, duration_frames)
    chains = _append_source_chains(root, state, media)

    entries = _build_video_entries(state, media)
    for track in (1, 2):
        _append_video_playlist(
            root,
            f"playlist_v{track}",
            [entry for entry in entries if entry["track"] == track],
            media,
            duration_frames,
            chains=chains,
            color=bool(extras and extras.color_filters),
        )

    _append_playlist(
        root,
        "playlist2",
        state.audio_segments,
        media,
        video=False,
        chains=chains,
        transitions=[clip.transition_out for clip in state.video_segments],
    )
    ET.SubElement(root, "playlist", {"id": "playlist3"})
    _append_track_tractor(root, "tractor1", "playlist2", "playlist3", audio=True)

    overlay = (
        _append_overlay_playlist(root, extras, media, duration_frames) if extras is not None else ""
    )
    stem = (
        _append_stem_playlist(root, extras, media, duration_frames)
        if extras is not None and extras.audio_stem
        else ""
    )
    music = (
        _append_music_playlist(root, extras, media, duration_frames)
        if extras is not None and extras.music
        else ""
    )
    captions = (
        _append_captions_playlist(root, extras, media, duration_frames)
        if extras is not None and extras.captions
        else ""
    )
    _append_sequence_tractor(
        root,
        sequence_id=sequence_id,
        duration=duration,
        duration_frames=duration_frames,
        media=media,
        video_tracks=("playlist_v1", "playlist_v2"),
        audio_track="tractor1",
        overlay=overlay,
        overlay_audio=stem,
        music=music,
        captions=captions,
    )
    _append_main_bin(
        root,
        sequence_id=sequence_id,
        document_id=document_id,
        sequence_uuid=str(sequence_uuid),
        media=media,
        extras=extras,
        chains=chains,
    )
    _append_final_tractor(root, sequence_id=sequence_id, duration=duration)

    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    return write_text(
        output_path,
        f'<?xml version="1.0" encoding="UTF-8"?>\n{body}\n',
    )


def _append_profile(parent: ET.Element, media) -> None:
    divisor = gcd(media.width, media.height)
    ET.SubElement(
        parent,
        "profile",
        {
            "colorspace": "709",
            "description": f"{media.width}x{media.height} {media.fps_num}/{media.fps_den} fps",
            "display_aspect_den": str(media.height // divisor),
            "display_aspect_num": str(media.width // divisor),
            "frame_rate_den": str(media.fps_den),
            "frame_rate_num": str(media.fps_num),
            "height": str(media.height),
            "progressive": "1",
            "sample_aspect_den": "1",
            "sample_aspect_num": "1",
            "width": str(media.width),
        },
    )


def _append_black_track(parent: ET.Element, duration: str, duration_frames: int) -> None:
    producer = ET.SubElement(
        parent,
        "producer",
        {"id": "black_track", "in": "00:00:00.000", "out": duration},
    )
    _property(producer, "length", str(duration_frames))
    _property(producer, "eof", "continue")
    _property(producer, "resource", "black")
    _property(producer, "mlt_service", "color")
    _property(producer, "kdenlive:playlistid", "black_track")
    _property(producer, "mlt_image_format", "rgba")
    _property(producer, "set.test_audio", "0")


def _source_order(state, media) -> list[tuple[str, object]]:
    """Primary source first, then every other source in project order."""

    if not state.sources:
        return [(state.primary_source_id or "primary", media)]
    ordered: list[tuple[str, object]] = []
    primary = state.primary_source_id or next(iter(state.sources))
    if primary in state.sources:
        ordered.append((primary, state.sources[primary]))
    for source_id, source_media in state.sources.items():
        if source_id != primary:
            ordered.append((source_id, source_media))
    return ordered


def _append_source_chains(parent: ET.Element, state, media) -> dict[str, str]:
    """Create one MLT chain per source so multicam edits stay native."""

    chains: dict[str, str] = {}
    for index, (source_id, source_media) in enumerate(_source_order(state, media)):
        chain_id = f"chain{index}"
        chains[source_id] = chain_id
        chain = ET.SubElement(parent, "chain", {"id": chain_id})
        path = Path(source_media.source_path).expanduser().resolve()
        _property(chain, "resource", str(path))
        _property(chain, "mlt_service", "avformat-novalidate")
        _property(chain, "kdenlive:clipname", path.name)
        _property(chain, "kdenlive:id", str(index + 1))
        _property(chain, "kdenlive:duration", str(source_media.duration_frames))
    return chains


def _build_video_entries(state, media) -> list[dict[str, object]]:
    """Alternate clips across two video tracks and size crossfade handles."""

    video = sorted(state.video_segments, key=lambda clip: clip.timeline_in_frame)
    entries: list[dict[str, object]] = []
    for index, clip in enumerate(video):
        entries.append(
            {
                "clip": clip,
                "source_id": clip.source_id or state.primary_source_id or "primary",
                "track": 1 if index % 2 == 0 else 2,
                "start": clip.timeline_in_frame,
                "source_in": clip.source_in_frame,
                "source_out": clip.source_out_frame,
                "fade_in": 0,
                "fade_out": 0,
            }
        )
    for index, clip in enumerate(video):
        transition = clip.transition_out
        if transition is None or index + 1 >= len(entries):
            continue
        current = entries[index]
        following = entries[index + 1]
        duration = max(0, transition.duration_frames)
        if duration == 0:
            continue
        if transition.type == "crossfade":
            if int(current["source_out"]) + duration > media.duration_frames:
                continue
            current["source_out"] = int(current["source_out"]) + duration
            if current["track"] == 2 and following["track"] == 1:
                current["fade_out"] = duration
            else:
                following["fade_in"] = duration
        elif transition.type == "fade_to_black":
            current["fade_out"] = duration
            following["fade_in"] = duration
    return entries


def _append_video_playlist(
    parent: ET.Element,
    playlist_id: str,
    entries: list[dict[str, object]],
    media,
    duration_frames: int,
    *,
    chains: dict[str, str],
    color: bool,
) -> None:
    playlist = ET.SubElement(parent, "playlist", {"id": playlist_id})
    cursor = 0
    for index, entry in enumerate(sorted(entries, key=lambda item: int(item["start"]))):
        start = int(entry["start"])
        source_in = int(entry["source_in"])
        source_out = int(entry["source_out"])
        if start < cursor:
            shift = cursor - start
            start = cursor
            source_in += shift
        length = source_out - source_in
        if length <= 0:
            continue
        if start > cursor:
            ET.SubElement(playlist, "blank", {"length": str(start - cursor)})
        item = ET.SubElement(
            playlist,
            "entry",
            {
                "producer": chains.get(
                    str(entry["source_id"]),
                    next(iter(chains.values()), "chain0"),
                ),
                "in": _timecode(source_in, media.fps_num, media.fps_den),
                "out": _timecode(source_out - 1, media.fps_num, media.fps_den),
            },
        )
        _append_video_filter(
            item,
            entry["clip"],
            media,
            length,
            index=index,
            color=color,
            fade_in=int(entry["fade_in"]),
            fade_out=int(entry["fade_out"]),
        )
        cursor = start + length
    if cursor < duration_frames:
        ET.SubElement(playlist, "blank", {"length": str(duration_frames - cursor)})


def _append_playlist(
    parent: ET.Element,
    playlist_id: str,
    clips: list,
    media,
    *,
    video: bool,
    chains: dict[str, str],
    transitions: list | None = None,
    color: bool = False,
) -> None:
    playlist = ET.SubElement(parent, "playlist", {"id": playlist_id})
    previous_transition = None
    for index, clip in enumerate(clips):
        current_transition = (
            clip.transition_out if video else (transitions[index] if transitions else None)
        )
        if video:
            source_in = clip.source_in_frame
            source_out = max(clip.source_in_frame, clip.source_out_frame - 1)
        else:
            source_in = media.timebase().sample_to_frame(clip.source_in_sample, Rounding.NEAREST)
            source_out = max(
                source_in,
                media.timebase().sample_to_frame(clip.source_out_sample, Rounding.CEIL) - 1,
            )
        duration_frames = source_out - source_in + 1
        entry = ET.SubElement(
            playlist,
            "entry",
            {
                "producer": chains.get(
                    clip.source_id or getattr(media, "source_id", ""),
                    next(iter(chains.values()), "chain0"),
                ),
                "in": _timecode(source_in, media.fps_num, media.fps_den),
                "out": _timecode(source_out, media.fps_num, media.fps_den),
            },
        )
        if video:
            _append_video_filter(
                entry,
                clip,
                media,
                duration_frames,
                previous_transition=previous_transition,
                index=index,
                color=color,
            )
        else:
            _append_volume_fade(
                entry,
                clip,
                media,
                duration_frames,
                previous_transition=previous_transition,
                current_transition=current_transition,
            )
        previous_transition = current_transition


def _append_track_tractor(
    parent: ET.Element,
    tractor_id: str,
    playlist_id: str,
    empty_playlist_id: str,
    *,
    audio: bool,
) -> None:
    tractor = ET.SubElement(parent, "tractor", {"id": tractor_id})
    if audio:
        _property(tractor, "kdenlive:audio_track", "1")
        ET.SubElement(tractor, "track", {"producer": playlist_id, "hide": "video"})
        ET.SubElement(tractor, "track", {"producer": empty_playlist_id, "hide": "video"})
    else:
        ET.SubElement(tractor, "track", {"producer": playlist_id, "hide": "audio"})
        ET.SubElement(tractor, "track", {"producer": empty_playlist_id, "hide": "audio"})


def _append_sequence_tractor(
    parent: ET.Element,
    *,
    sequence_id: str,
    duration: str,
    duration_frames: int,
    media,
    video_tracks: tuple[str, str],
    audio_track: str,
    overlay: str = "",
    overlay_audio: str = "",
    music: str = "",
    captions: str = "",
) -> None:
    tracks = (
        3
        + (1 if overlay else 0)
        + (1 if overlay_audio else 0)
        + (1 if music else 0)
        + (1 if captions else 0)
    )
    tractor = ET.SubElement(
        parent,
        "tractor",
        {"id": sequence_id, "in": "00:00:00.000", "out": duration},
    )
    _property(tractor, "kdenlive:uuid", sequence_id)
    _property(tractor, "kdenlive:clipname", "VideoFlow")
    _property(tractor, "kdenlive:sequenceproperties.hasAudio", "1")
    _property(tractor, "kdenlive:sequenceproperties.hasVideo", "1")
    _property(tractor, "kdenlive:sequenceproperties.activeTrack", "1")
    _property(tractor, "kdenlive:sequenceproperties.tracksCount", str(tracks))
    _property(tractor, "kdenlive:sequenceproperties.documentuuid", sequence_id)
    _property(tractor, "kdenlive:producer_type", "17")
    _property(tractor, "kdenlive:id", "3")
    _property(tractor, "kdenlive:clip_type", "0")
    _property(tractor, "kdenlive:folderid", "2")
    _property(tractor, "kdenlive:sequenceproperties.audioTarget", "3")
    _property(tractor, "kdenlive:sequenceproperties.videoTarget", "1")
    _property(tractor, "kdenlive:sequenceproperties.tracks", str(tracks))
    _property(tractor, "kdenlive:sequenceproperties.zonein", "0")
    _property(tractor, "kdenlive:sequenceproperties.zoneout", str(duration_frames))

    ET.SubElement(tractor, "track", {"producer": "black_track"})
    _append_transition(tractor, "transition-v1", 1, "qtblend")
    _append_transition(tractor, "transition-v2", 2, "qtblend")
    ET.SubElement(tractor, "track", {"producer": video_tracks[0]})
    ET.SubElement(tractor, "track", {"producer": video_tracks[1]})
    ET.SubElement(tractor, "track", {"producer": audio_track})
    _append_transition(tractor, "transition-audio", 3, "mix")
    if overlay:
        ET.SubElement(tractor, "track", {"producer": overlay})
        _append_transition(tractor, "transition-overlay", 4, "qtblend")
    if overlay_audio:
        ET.SubElement(tractor, "track", {"producer": overlay_audio})
        _append_transition(tractor, "transition-stem", 5, "mix")
    if music:
        ET.SubElement(tractor, "track", {"producer": music})
        _append_transition(tractor, "transition-music", 5 + (1 if overlay_audio else 0), "mix")
    if captions:
        ET.SubElement(tractor, "track", {"producer": captions})
        _append_transition(
            tractor,
            "transition-captions",
            5 + (1 if overlay_audio else 0) + (1 if music else 0),
            "qtblend",
        )


def _append_transition(
    parent: ET.Element,
    transition_id: str,
    b_track: int,
    service: str,
) -> None:
    transition = ET.SubElement(parent, "transition", {"id": transition_id})
    _property(transition, "a_track", "0")
    _property(transition, "b_track", str(b_track))
    _property(transition, "mlt_service", service)
    _property(transition, "kdenlive_id", service)
    _property(transition, "internal_added", "237")
    _property(transition, "always_active", "1")
    if service == "mix":
        _property(transition, "sum", "1")


def _append_main_bin(
    parent: ET.Element,
    *,
    sequence_id: str,
    document_id: str,
    sequence_uuid: str,
    media,
    extras=None,
    chains: dict[str, str] | None = None,
) -> None:
    main_bin = ET.SubElement(parent, "playlist", {"id": "main_bin"})
    if extras is not None:
        _append_guides(main_bin, extras, media)
    _property(main_bin, "kdenlive:folder.-1.2", "Sequences")
    _property(main_bin, "kdenlive:sequenceFolder", "2")
    _property(main_bin, "kdenlive:docproperties.audioChannels", "1")
    _property(main_bin, "kdenlive:docproperties.binsort", "0")
    _property(main_bin, "kdenlive:docproperties.documentid", document_id)
    _property(main_bin, "kdenlive:docproperties.uuid", sequence_id)
    _property(main_bin, "kdenlive:docproperties.version", "1.1")
    _property(main_bin, "kdenlive:docproperties.kdenliveversion", "25.04.0")
    _property(main_bin, "kdenlive:docproperties.activetimeline", sequence_id)
    _property(main_bin, "kdenlive:docproperties.opensequences", sequence_id)
    _property(main_bin, "kdenlive:expandedFolders", "")
    _property(main_bin, "kdenlive:binZoom", "4")
    _property(main_bin, "xml_retain", "1")
    ET.SubElement(
        main_bin,
        "entry",
        {"in": "00:00:00.000", "out": "00:00:00.000", "producer": sequence_id},
    )
    for chain_id in (chains or {"": "chain0"}).values():
        ET.SubElement(
            main_bin,
            "entry",
            {"in": "00:00:00.000", "out": "00:00:00.000", "producer": chain_id},
        )


def _append_final_tractor(parent: ET.Element, *, sequence_id: str, duration: str) -> None:
    tractor = ET.SubElement(
        parent,
        "tractor",
        {"id": "final_tractor", "in": "00:00:00.000", "out": duration},
    )
    _property(tractor, "kdenlive:projectTractor", "1")
    ET.SubElement(
        tractor,
        "track",
        {"in": "00:00:00.000", "out": duration, "producer": sequence_id},
    )


def _property(parent: ET.Element, name: str, value: str) -> None:
    ET.SubElement(parent, "property", {"name": name}).text = value


def _append_volume_fade(
    entry: ET.Element,
    clip,
    media,
    duration_frames: int,
    *,
    previous_transition=None,
    current_transition=None,
) -> None:
    fade_in = media.timebase().sample_to_frame(clip.fade_in_samples, Rounding.CEIL)
    fade_out = media.timebase().sample_to_frame(clip.fade_out_samples, Rounding.CEIL)
    if previous_transition is not None and previous_transition.audio:
        fade_in = max(fade_in, previous_transition.duration_frames)
    if current_transition is not None and current_transition.audio:
        fade_out = max(fade_out, current_transition.duration_frames)
    if fade_in <= 0 and fade_out <= 0:
        return
    fade_in = min(fade_in, max(0, duration_frames - 1))
    fade_out = min(fade_out, max(0, duration_frames - 1))
    points: list[tuple[int, int]] = []
    if fade_in > 0:
        points.extend([(0, -60), (fade_in, 0)])
    else:
        points.append((0, 0))
    if fade_out > 0:
        points.append((max(0, duration_frames - 1 - fade_out), 0))
        points.append((max(0, duration_frames - 1), -60))
    level = ";".join(f"{frame}={value}" for frame, value in points)
    filter_element = ET.SubElement(
        entry,
        "filter",
        {
            "id": f"filter-{clip.clip_id}",
            "in": _timecode(0, media.fps_num, media.fps_den),
            "out": _timecode(max(0, duration_frames - 1), media.fps_num, media.fps_den),
        },
    )
    _property(filter_element, "window", "75")
    _property(filter_element, "max_gain", "20dB")
    _property(filter_element, "mlt_service", "volume")
    _property(filter_element, "kdenlive_id", "volume")
    _property(filter_element, "level", level)


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


def _transform_rect(
    media,
    scale: float,
    pos_x: float,
    pos_y: float,
    anchor: str,
    pan_direction: str,
    opacity: float,
) -> tuple[int, int, int, int, float]:
    width = round(media.width * scale)
    height = round(media.height * scale)
    x = round((media.width - width) / 2 + pos_x * media.width)
    y = round((media.height - height) / 2 + pos_y * media.height)
    if anchor == "upper_third":
        y -= round((height - media.height) / 3)
    if pan_direction == "left_to_right":
        x -= media.width // 12
    elif pan_direction == "right_to_left":
        x += media.width // 12
    return x, y, width, height, opacity


def _timecode(frame: int, fps_num: int, fps_den: int) -> str:
    total_ms = round(max(0, frame) * fps_den * 1000 / fps_num)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


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


def _append_guides(main_bin: ET.Element, extras, media) -> None:
    if extras is None or not extras.markers:
        return
    fps = media.fps_num / media.fps_den
    guides = [
        {
            "comment": marker.name if not marker.note else f"{marker.name}: {marker.note}",
            "pos": round(marker.start_sec * fps),
            "type": 0,
            "color": marker.color or "#38bdf8",
        }
        for marker in extras.markers
    ]
    import json

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
