"""XMEML helper: music, quarantine, titles, captions and B-roll."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from videoflow.domain.state import MediaInfo, ProjectState
from videoflow.exporters.extras import NleExtras

from .common import (
    _append_basic_motion,
    _append_file,
    _append_rate,
    _premiere_path_url,
)


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
