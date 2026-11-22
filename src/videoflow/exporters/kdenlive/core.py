"""Kdenlive helper: project skeleton."""

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

from .common import _property, _timecode
from .extras import (
    _append_captions_playlist,
    _append_music_playlist,
    _append_overlay_playlist,
    _append_stem_playlist,
)
from .tracks import (
    _append_final_tractor,
    _append_main_bin,
    _append_playlist,
    _append_sequence_tractor,
    _append_track_tractor,
    _append_video_playlist,
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
        state=state,
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
