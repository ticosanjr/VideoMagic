"""Shared export checks and formatting."""

from __future__ import annotations

import os
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path

from videoflow.domain.errors import ExportError
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.domain.timebase import Rounding, Timebase


def require_timeline(
    state: ProjectState,
) -> tuple[MediaInfo, dict[str, VideoSegment], dict[str, AudioSegment]]:
    """Validate the shared preconditions every exporter relies on."""

    media = state.media_info
    if media is None:
        raise ExportError("Project has no media")
    if not Path(media.source_path).is_file():
        raise ExportError(f"Source media is offline: {media.source_path}")
    if not state.video_segments:
        raise ExportError("Timeline has no video segments")

    video_by_id = _unique(state.video_segments, "video")
    audio_by_id = _unique(state.audio_segments, "audio")
    if set(video_by_id) != set(audio_by_id):
        missing = sorted(set(video_by_id) - set(audio_by_id))
        extra = sorted(set(audio_by_id) - set(video_by_id))
        raise ExportError(f"Audio/video clip mismatch. Missing audio: {missing}. Extra: {extra}.")

    for clip in state.video_segments:
        clip_media = state.video_media(clip) or media
        if not Path(clip_media.source_path).is_file():
            raise ExportError(f"Source media is offline: {clip_media.source_path}")
        if clip.source_out_frame > clip_media.duration_frames:
            raise ExportError(f"Clip {clip.clip_id} exceeds the media duration")
    for clip in state.audio_segments:
        clip_media = state.audio_media(clip) or media
        clip_samples = clip_media.timebase().seconds_to_samples(
            clip_media.timebase().frames_to_seconds(clip_media.duration_frames),
            Rounding.NEAREST,
        )
        if clip.source_out_sample > clip_samples:
            raise ExportError(f"Audio clip {clip.clip_id} exceeds the media duration")

    video_spans = [
        (item.timeline_in_frame, item.timeline_out_frame) for item in state.video_segments
    ]
    audio_spans = [
        (item.timeline_in_sample, item.timeline_out_sample) for item in state.audio_segments
    ]
    video_gap = _first_gap(video_spans)
    if video_gap is not None:
        raise ExportError(
            "Video timeline is not packed from frame zero "
            f"(first gap at frames {video_gap[0]}-{video_gap[1]})"
        )
    audio_gap = _first_gap(audio_spans)
    if audio_gap is not None:
        raise ExportError(
            "Audio timeline is not packed from sample zero "
            f"(first gap at samples {audio_gap[0]}-{audio_gap[1]})"
        )

    return media, video_by_id, audio_by_id


def timeline_duration_frames(state: ProjectState) -> int:
    return max(item.timeline_out_frame for item in state.video_segments)


def timeline_duration_samples(state: ProjectState) -> int:
    return max(item.timeline_out_sample for item in state.audio_segments)


def rate_parts(media: MediaInfo) -> Timebase:
    return media.timebase()


def file_uri(path: str) -> str:
    return Path(path).expanduser().resolve().as_uri()


def write_text(path: Path, text: str) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f"{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, target)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise
    return target


def xml_document(root: ET.Element, doctype: str) -> str:
    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE {doctype}>\n{body}\n'


def _first_gap(spans: Sequence[tuple[int, int]], *, origin: int = 0) -> tuple[int, int] | None:
    """Return the first missing or invalid span, if any."""

    ordered = sorted(spans)
    if not ordered:
        return None
    if ordered[0][0] != origin:
        return (origin, ordered[0][0])
    cursor = origin
    for start, end in ordered:
        if end < start:
            return (start, end)
        if start != cursor:
            return (cursor, start)
        cursor = end
    return None


def _unique(
    items: list[VideoSegment] | list[AudioSegment],
    label: str,
) -> dict[str, VideoSegment] | dict[str, AudioSegment]:
    result: dict[str, VideoSegment] | dict[str, AudioSegment] = {}
    for item in items:
        if item.clip_id in result:
            raise ExportError(f"Duplicate {label} clip id: {item.clip_id}")
        result[item.clip_id] = item
    return result
