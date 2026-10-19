"""Shared export checks and formatting."""

from __future__ import annotations

import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from videoflow.domain.errors import ExportError
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.domain.timebase import Rounding, Timebase
from videoflow.domain.timeline import is_packed


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

    timebase = media.timebase()
    media_samples = timebase.seconds_to_samples(
        timebase.frames_to_seconds(media.duration_frames), Rounding.NEAREST
    )
    for clip in state.video_segments:
        if clip.source_out_frame > media.duration_frames:
            raise ExportError(f"Clip {clip.clip_id} exceeds the media duration")
    for clip in state.audio_segments:
        if clip.source_out_sample > media_samples:
            raise ExportError(f"Audio clip {clip.clip_id} exceeds the media duration")

    video_spans = [
        (item.timeline_in_frame, item.timeline_out_frame) for item in state.video_segments
    ]
    audio_spans = [
        (item.timeline_in_sample, item.timeline_out_sample) for item in state.audio_segments
    ]
    if not is_packed(video_spans):
        raise ExportError("Video timeline is not packed from frame zero")
    if not is_packed(audio_spans):
        raise ExportError("Audio timeline is not packed from sample zero")

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
