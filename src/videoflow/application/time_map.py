"""Bidirectional mapping between source time and the edited timeline.

The canonical timeline already stores ``source_in/out`` and ``timeline_in/out``
on every segment. This module turns that data into a compact, persisted table
and provides the conversion used by the MCP tools that accept ``time_basis``.
"""

from __future__ import annotations

from fractions import Fraction

from videoflow.domain.state import ProjectState, TimeMapEntry
from videoflow.domain.timebase import Rounding

TIME_BASES = ("timeline", "source")


class TimeMapError(ValueError):
    """Raised when a requested time falls outside every mapped segment."""


def build_time_map(state: ProjectState) -> list[TimeMapEntry]:
    """Return one entry per video segment, ordered by timeline position."""

    entries: list[TimeMapEntry] = []
    for clip in sorted(state.video_segments, key=lambda item: item.timeline_in_frame):
        media = state.video_media(clip)
        if media is None:
            continue
        timebase = media.timebase()
        entries.append(
            TimeMapEntry(
                source_id=clip.source_id,
                source_in_frame=clip.source_in_frame,
                source_out_frame=clip.source_out_frame,
                timeline_in_frame=clip.timeline_in_frame,
                timeline_out_frame=clip.timeline_out_frame,
                source_in_sample=timebase.frame_start_sample(clip.source_in_frame),
                source_out_sample=timebase.frame_to_sample(clip.source_out_frame, Rounding.NEAREST),
                timeline_in_sample=timebase.frame_start_sample(clip.timeline_in_frame),
                timeline_out_sample=timebase.frame_start_sample(clip.timeline_out_frame),
                fps_num=media.fps_num,
                fps_den=media.fps_den,
                sample_rate=media.audio_sample_rate,
            )
        )
    return entries


def refresh_time_map(state: ProjectState) -> ProjectState:
    """Return a copy of ``state`` with the pipeline time table rebuilt."""

    entries = build_time_map(state)
    return state.model_copy(
        update={"pipeline": state.pipeline.model_copy(update={"time_map": entries})}
    )


def _timeline_rate(state: ProjectState) -> tuple[int, int]:
    media = state.media_info
    if media is None:
        return 30, 1
    return media.fps_num, media.fps_den


def _seconds(value: float) -> Fraction:
    return Fraction(str(max(0.0, float(value))))


def compact_time_map(state: ProjectState) -> list[list[float]]:
    """Return ``[[source_in, source_out, edited_in, edited_out], ...]`` in seconds."""

    ranges: list[list[float]] = []
    for entry in build_time_map(state):
        fps = entry.fps_num / max(1, entry.fps_den)
        ranges.append(
            [
                round(entry.source_in_frame / fps, 6),
                round(entry.source_out_frame / fps, 6),
                round(entry.timeline_in_frame / fps, 6),
                round(entry.timeline_out_frame / fps, 6),
            ]
        )
    return ranges


def source_to_timeline_sec(
    state: ProjectState,
    source_sec: float,
    *,
    source_id: str = "",
) -> float:
    """Map a source timestamp to timeline seconds.

    Source ranges that were cut out have no mapping and raise ``TimeMapError``.
    """

    source = float(source_sec)
    for entry in build_time_map(state):
        if source_id and entry.source_id != source_id:
            continue
        start = entry.source_in_frame / (entry.fps_num / entry.fps_den)
        end = entry.source_out_frame / (entry.fps_num / entry.fps_den)
        if source < start - 1e-6 or source > end + 1e-6:
            continue
        source_frame = source * entry.fps_num / entry.fps_den
        timeline_frame = entry.timeline_in_frame + (source_frame - entry.source_in_frame)
        fps_num, fps_den = _timeline_rate(state)
        return max(0.0, timeline_frame * fps_den / fps_num)
    raise TimeMapError(f"source time {source_sec:g}s is outside the edited timeline")


def timeline_to_source_sec(state: ProjectState, timeline_sec: float) -> float:
    """Map a timeline timestamp back to the original source timestamp."""

    timeline = float(timeline_sec)
    fps_num, fps_den = _timeline_rate(state)
    timeline_frame = timeline * fps_num / fps_den
    entries = build_time_map(state)
    for index, entry in enumerate(entries):
        if timeline_frame < entry.timeline_in_frame - 1e-6:
            continue
        boundary = abs(timeline_frame - entry.timeline_out_frame) <= 1e-6
        if boundary and index + 1 < len(entries):
            # Prefer the next segment at a shared cut boundary.
            continue
        if timeline_frame > entry.timeline_out_frame + 1e-6:
            continue
        source_frame = entry.source_in_frame + (timeline_frame - entry.timeline_in_frame)
        return max(0.0, source_frame * entry.fps_den / entry.fps_num)
    raise TimeMapError(f"timeline time {timeline_sec:g}s is outside every segment")


def timeline_range_to_source_ranges(
    state: ProjectState,
    start_sec: float,
    end_sec: float,
) -> list[tuple[str, float, float]]:
    """Split a timeline range into the surviving source ranges."""

    start = max(0.0, float(start_sec))
    end = float(end_sec)
    if end <= start:
        raise TimeMapError("range end must be greater than range start")
    ranges: list[tuple[str, float, float]] = []
    for entry in build_time_map(state):
        fps = entry.fps_num / max(1, entry.fps_den)
        entry_start = entry.timeline_in_frame / fps
        entry_end = entry.timeline_out_frame / fps
        left = max(start, entry_start)
        right = min(end, entry_end)
        if right <= left:
            continue
        source_start = entry.source_in_frame / fps + (left - entry_start)
        source_end = entry.source_in_frame / fps + (right - entry_start)
        if source_end > source_start:
            ranges.append((entry.source_id, source_start, source_end))
    if not ranges:
        raise TimeMapError(
            f"timeline range {start_sec:g}-{end_sec:g}s is outside the edited timeline"
        )
    return ranges


def source_range_to_timeline(
    state: ProjectState,
    start_sec: float,
    end_sec: float,
    *,
    source_id: str = "",
) -> list[tuple[float, float]]:
    """Split a source range into the timeline ranges that survived the edit."""

    if end_sec <= start_sec:
        raise TimeMapError("range end must be greater than range start")
    ranges: list[tuple[float, float]] = []
    for entry in build_time_map(state):
        if source_id and entry.source_id != source_id:
            continue
        entry_start = entry.source_in_frame / (entry.fps_num / entry.fps_den)
        entry_end = entry.source_out_frame / (entry.fps_num / entry.fps_den)
        start = max(float(start_sec), entry_start)
        end = min(float(end_sec), entry_end)
        if end <= start:
            continue
        timeline_start = source_to_timeline_sec(state, start, source_id=entry.source_id)
        timeline_end = source_to_timeline_sec(state, end, source_id=entry.source_id)
        if timeline_end > timeline_start:
            ranges.append((timeline_start, timeline_end))
    if not ranges:
        raise TimeMapError(
            f"source range {start_sec:g}-{end_sec:g}s does not intersect the timeline"
        )
    return ranges


__all__ = [
    "TIME_BASES",
    "TimeMapError",
    "build_time_map",
    "refresh_time_map",
    "source_range_to_timeline",
    "source_to_timeline_sec",
    "timeline_range_to_source_ranges",
    "timeline_to_source_sec",
]


def last_speech_timeline_sec(state: ProjectState) -> float | None:
    """Return the last kept speech timestamp on the edited timeline."""

    media = state.media_info
    if media is None or not state.transcript:
        return None
    discard = set(state.pipeline.discard_sentence_ids)
    ends: list[float] = []
    for sentence in state.transcript:
        if sentence.id in discard:
            continue
        samples = [word.end_sample for word in sentence.words] or [sentence.end_sample]
        for sample in samples:
            source_sec = sample / max(1, media.audio_sample_rate)
            try:
                ends.append(source_to_timeline_sec(state, source_sec))
            except TimeMapError:
                continue
    return max(ends) if ends else None
