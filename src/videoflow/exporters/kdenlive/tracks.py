"""Kdenlive helper: playlists and tractors."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from videoflow.domain.timebase import Rounding

from .common import _append_volume_fade, _property, _timecode
from .extras import _append_guides, _append_video_filter


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
    state=None,
) -> None:
    main_bin = ET.SubElement(parent, "playlist", {"id": "main_bin"})
    _append_guides(main_bin, extras, media, state)
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
