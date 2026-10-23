"""Validated timeline edits over the canonical ProjectState document."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from videoflow.domain.errors import InvalidTimeError
from videoflow.domain.state import ProjectState
from videoflow.domain.timebase import Rounding

TimelineAction = Literal["trim", "move", "delete", "split", "ripple", "ripple_trim"]


@dataclass(frozen=True, slots=True)
class TimelineEdit:
    clip_id: str
    action: TimelineAction
    start_sec: float | None = None
    end_sec: float | None = None
    delta_sec: float = 0.0
    split_sec: float | None = None


def _fps(state: ProjectState) -> float:
    media = state.media_info
    if media is None:
        raise InvalidTimeError("Timeline edit requires media info.")
    return media.fps_num / media.fps_den


def _new_clip_id(existing: set[str], base: str) -> str:
    for _ in range(50):
        candidate = f"{base}-{uuid4().hex[:6]}"
        if candidate not in existing:
            return candidate
    raise InvalidTimeError("Could not allocate a clip id.")


def _shift_after_delete(state: ProjectState, clip_id: str, *, ripple: bool) -> None:
    video = next((clip for clip in state.video_segments if clip.clip_id == clip_id), None)
    if video is None:
        raise InvalidTimeError(f"Unknown clip: {clip_id}")
    media = state.media_info
    audio = next((clip for clip in state.audio_segments if clip.clip_id == clip_id), None)
    video_gap = video.timeline_out_frame - video.timeline_in_frame
    deleted_end_frame = video.timeline_out_frame
    audio_gap = (
        audio.timeline_out_sample - audio.timeline_in_sample
        if audio is not None
        else 0
    )
    deleted_end_sample = (
        audio.timeline_out_sample
        if audio is not None
        else media.timebase().frame_start_sample(deleted_end_frame) if media else 0
    )
    state.video_segments = [
        clip for clip in state.video_segments if clip.clip_id != clip_id
    ]
    state.audio_segments = [
        clip for clip in state.audio_segments if clip.clip_id != clip_id
    ]
    if not ripple:
        return
    for clip in state.video_segments:
        if clip.timeline_in_frame >= deleted_end_frame:
            clip.timeline_in_frame = max(0, clip.timeline_in_frame - video_gap)
            clip.timeline_out_frame = max(
                clip.timeline_in_frame + 1, clip.timeline_out_frame - video_gap
            )
    for clip in state.audio_segments:
        if clip.timeline_in_sample >= deleted_end_sample:
            shift = audio_gap or (
                media.timebase().frame_start_sample(video_gap) if media else 0
            )
            clip.timeline_in_sample = max(0, clip.timeline_in_sample - shift)
            clip.timeline_out_sample = max(
                clip.timeline_in_sample + 1, clip.timeline_out_sample - shift
            )


def _split_video(state: ProjectState, clip_id: str, split_sec: float) -> None:
    media = state.media_info
    if media is None:
        raise InvalidTimeError("Timeline edit requires media info.")
    fps = _fps(state)
    index, video = next(
        ((idx, clip) for idx, clip in enumerate(state.video_segments) if clip.clip_id == clip_id),
        (-1, None),
    )
    if video is None:
        raise InvalidTimeError(f"Unknown clip: {clip_id}")
    split_frame = round(split_sec * fps)
    if not (video.timeline_in_frame < split_frame < video.timeline_out_frame):
        raise InvalidTimeError("Split point must be inside the clip.")
    timeline_length = video.timeline_out_frame - video.timeline_in_frame
    source_length = video.source_out_frame - video.source_in_frame
    offset_frames = split_frame - video.timeline_in_frame
    source_split = video.source_in_frame + round(
        offset_frames * source_length / max(1, timeline_length)
    )
    source_split = max(video.source_in_frame + 1, min(video.source_out_frame - 1, source_split))
    existing = {clip.clip_id for clip in state.video_segments}
    right_id = _new_clip_id(existing, clip_id)
    right = video.model_copy(
        update={
            "clip_id": right_id,
            "source_in_frame": source_split,
            "timeline_in_frame": split_frame,
        }
    )
    left = video.model_copy(
        update={
            "source_out_frame": source_split,
            "timeline_out_frame": split_frame,
            "transition_out": None,
        }
    )
    state.video_segments[index] = left
    state.video_segments.insert(index + 1, right)

    audio_index = next(
        (idx for idx, clip in enumerate(state.audio_segments) if clip.clip_id == clip_id),
        -1,
    )
    if audio_index >= 0:
        audio = state.audio_segments[audio_index]
        split_sample = media.timebase().frame_start_sample(split_frame)
        if not (audio.timeline_in_sample < split_sample < audio.timeline_out_sample):
            return
        audio_timeline = audio.timeline_out_sample - audio.timeline_in_sample
        audio_source = audio.source_out_sample - audio.source_in_sample
        audio_offset = split_sample - audio.timeline_in_sample
        source_split_sample = audio.source_in_sample + round(
            audio_offset * audio_source / max(1, audio_timeline)
        )
        source_split_sample = max(
            audio.source_in_sample + 1,
            min(audio.source_out_sample - 1, source_split_sample),
        )
        audio_right = audio.model_copy(
            update={
                "clip_id": right_id,
                "source_in_sample": source_split_sample,
                "timeline_in_sample": split_sample,
            }
        )
        audio_left = audio.model_copy(
            update={
                "source_out_sample": source_split_sample,
                "timeline_out_sample": split_sample,
                "fade_out_samples": 0,
            }
        )
        state.audio_segments[audio_index] = audio_left
        state.audio_segments.insert(audio_index + 1, audio_right)


def _ripple_trim(
    state: ProjectState,
    edit: TimelineEdit,
    *,
    fps: float,
    media,
) -> None:
    video = next((clip for clip in state.video_segments if clip.clip_id == edit.clip_id), None)
    if video is None:
        raise InvalidTimeError(f"Unknown clip: {edit.clip_id}")
    audio = next((clip for clip in state.audio_segments if clip.clip_id == edit.clip_id), None)
    old_end_frame = video.timeline_out_frame
    old_end_sample = audio.timeline_out_sample if audio is not None else 0
    apply_timeline_edit(
        state,
        TimelineEdit(
            clip_id=edit.clip_id,
            action="trim",
            start_sec=edit.start_sec,
            end_sec=edit.end_sec,
        ),
    )
    new_end_frame = video.timeline_out_frame
    frame_delta = new_end_frame - old_end_frame
    if frame_delta:
        for clip in state.video_segments:
            if clip is video:
                continue
            if clip.timeline_in_frame >= old_end_frame:
                clip.timeline_in_frame = max(0, clip.timeline_in_frame + frame_delta)
                clip.timeline_out_frame = max(
                    clip.timeline_in_frame + 1, clip.timeline_out_frame + frame_delta
                )
    if audio is not None:
        sample_delta = audio.timeline_out_sample - old_end_sample
        if sample_delta:
            for clip in state.audio_segments:
                if clip is audio:
                    continue
                if clip.timeline_in_sample >= old_end_sample:
                    clip.timeline_in_sample = max(
                        0, clip.timeline_in_sample + sample_delta
                    )
                    clip.timeline_out_sample = max(
                        clip.timeline_in_sample + 1,
                        clip.timeline_out_sample + sample_delta,
                    )


def apply_timeline_edit(state: ProjectState, edit: TimelineEdit) -> ProjectState:
    fps = _fps(state)
    media = state.media_info
    assert media is not None
    video = next((clip for clip in state.video_segments if clip.clip_id == edit.clip_id), None)
    if video is None:
        raise InvalidTimeError(f"Unknown clip: {edit.clip_id}")
    audio = next((clip for clip in state.audio_segments if clip.clip_id == edit.clip_id), None)

    if edit.action == "delete":
        _shift_after_delete(state, edit.clip_id, ripple=False)
        return state

    if edit.action == "ripple":
        _shift_after_delete(state, edit.clip_id, ripple=True)
        return state

    if edit.action == "ripple_trim":
        if edit.start_sec is None or edit.end_sec is None:
            raise InvalidTimeError("Ripple trim requires start and end.")
        _ripple_trim(state, edit, fps=fps, media=media)
        return state

    if edit.action == "split":
        if edit.split_sec is None:
            raise InvalidTimeError("Split requires split_sec.")
        _split_video(state, edit.clip_id, max(0.0, edit.split_sec))
        return state

    if edit.action == "move":
        delta_frames = round(edit.delta_sec * fps)
        if video.timeline_in_frame + delta_frames < 0:
            raise InvalidTimeError("Move would place the clip before zero.")
        video.timeline_in_frame += delta_frames
        video.timeline_out_frame += delta_frames
        if audio is not None:
            delta_samples = round(edit.delta_sec * media.audio_sample_rate)
            if audio.timeline_in_sample + delta_samples < 0:
                raise InvalidTimeError("Move would place the audio before zero.")
            audio.timeline_in_sample += delta_samples
            audio.timeline_out_sample += delta_samples
        return state

    if edit.start_sec is None or edit.end_sec is None:
        raise InvalidTimeError("Trim requires start and end.")
    start = round(max(0.0, edit.start_sec) * fps)
    end = round(max(0.0, edit.end_sec) * fps)
    if end <= start:
        raise InvalidTimeError("Trim end must be after start.")
    old_timeline = video.timeline_out_frame - video.timeline_in_frame
    old_source = video.source_out_frame - video.source_in_frame
    if old_timeline <= 0 or old_source <= 0:
        raise InvalidTimeError("Clip has no duration.")
    source_ratio = old_source / old_timeline
    new_source_in = video.source_in_frame + round(
        (start - video.timeline_in_frame) * source_ratio
    )
    new_source_out = new_source_in + round((end - start) * source_ratio)
    if new_source_in < 0 or new_source_out > media.duration_frames:
        raise InvalidTimeError("Trim exceeds source media.")
    video.timeline_in_frame, video.timeline_out_frame = start, end
    video.source_in_frame, video.source_out_frame = new_source_in, new_source_out

    if audio is not None:
        old_audio_timeline = audio.timeline_out_sample - audio.timeline_in_sample
        old_audio_source = audio.source_out_sample - audio.source_in_sample
        audio_ratio = old_audio_source / max(1, old_audio_timeline)
        new_audio_start = media.timebase().frame_to_sample(start, Rounding.NEAREST)
        new_audio_end = media.timebase().frame_to_sample(end, Rounding.CEIL)
        new_audio_source_in = audio.source_in_sample + round(
            (new_audio_start - audio.timeline_in_sample) * audio_ratio
        )
        new_audio_source_out = new_audio_source_in + round(
            (new_audio_end - new_audio_start) * audio_ratio
        )
        audio.timeline_in_sample = max(0, new_audio_start)
        audio.timeline_out_sample = max(audio.timeline_in_sample + 1, new_audio_end)
        audio.source_in_sample = max(0, new_audio_source_in)
        media_samples = round(media.duration_frames * media.audio_sample_rate / max(0.001, fps))
        audio.source_out_sample = min(
            media_samples,
            max(audio.source_in_sample + 1, new_audio_source_out),
        )
    return state


def timeline_duration_sec(state: ProjectState) -> float:
    fps = _fps(state)
    return max((clip.timeline_out_frame for clip in state.video_segments), default=0) / max(
        0.001, fps
    )
