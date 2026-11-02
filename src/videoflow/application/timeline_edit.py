"""Validated timeline edits over the canonical ProjectState document."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from videoflow.domain.errors import InvalidTimeError
from videoflow.domain.state import InactiveSegment, ProjectState
from videoflow.domain.timebase import Rounding

TimelineAction = Literal[
    "trim", "move", "delete", "split", "ripple", "ripple_trim", "slip",
    "slide", "duplicate", "deactivate", "activate", "recut",
]


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


def _repack_timeline(state: ProjectState) -> None:
    """Reassign packed timeline positions after a visibility toggle."""

    video = sorted(state.video_segments, key=lambda clip: clip.timeline_in_frame)
    cursor = 0
    for clip in video:
        duration = max(1, clip.timeline_out_frame - clip.timeline_in_frame)
        clip.timeline_in_frame = cursor
        clip.timeline_out_frame = cursor + duration
        cursor += duration
    state.video_segments = video

    audio_by_id = {clip.clip_id: clip for clip in state.audio_segments}
    ordered_audio: list = []
    sample_cursor = 0
    for clip in video:
        audio = audio_by_id.get(clip.clip_id)
        if audio is None:
            continue
        duration = max(1, audio.timeline_out_sample - audio.timeline_in_sample)
        audio.timeline_in_sample = sample_cursor
        audio.timeline_out_sample = sample_cursor + duration
        sample_cursor += duration
        ordered_audio.append(audio)
    state.audio_segments = ordered_audio


def _deactivate_clip(state: ProjectState, clip_id: str, *, reason: str = "manual") -> None:
    video = next((clip for clip in state.video_segments if clip.clip_id == clip_id), None)
    audio = next((clip for clip in state.audio_segments if clip.clip_id == clip_id), None)
    if video is None or audio is None:
        raise InvalidTimeError(f"Unknown active clip: {clip_id}")
    state.video_segments = [clip for clip in state.video_segments if clip.clip_id != clip_id]
    state.audio_segments = [clip for clip in state.audio_segments if clip.clip_id != clip_id]
    state.inactive_segments = [
        item for item in state.inactive_segments if item.clip_id != clip_id
    ] + [
        InactiveSegment(
            clip_id=clip_id,
            video=video.model_copy(deep=True),
            audio=audio.model_copy(deep=True),
            reason=reason,  # type: ignore[arg-type]
        )
    ]
    for clip in state.video_segments:
        clip.transition_out = None
    _repack_timeline(state)


def _activate_clip(state: ProjectState, clip_id: str) -> None:
    inactive = next(
        (item for item in state.inactive_segments if item.clip_id == clip_id), None
    )
    if inactive is None:
        raise InvalidTimeError(f"Unknown inactive clip: {clip_id}")
    if any(clip.clip_id == clip_id for clip in state.video_segments):
        raise InvalidTimeError(f"Clip is already active: {clip_id}")
    video = inactive.video.model_copy(deep=True)
    audio = inactive.audio.model_copy(deep=True)
    video.transition_out = None
    video.timeline_in_frame = 0
    video.timeline_out_frame = max(
        1, inactive.video.timeline_out_frame - inactive.video.timeline_in_frame
    )
    audio.timeline_in_sample = 0
    audio.timeline_out_sample = max(
        1, inactive.audio.timeline_out_sample - inactive.audio.timeline_in_sample
    )
    active = list(state.video_segments)
    position = len(active)
    for index, clip in enumerate(active):
        if clip.source_in_frame > video.source_in_frame:
            position = index
            break
    active.insert(position, video)
    state.video_segments = active
    state.audio_segments = list(state.audio_segments) + [audio]
    for clip in state.video_segments:
        clip.transition_out = None
    state.inactive_segments = [
        item for item in state.inactive_segments if item.clip_id != clip_id
    ]
    _repack_timeline(state)


def _recut_inactive(
    state: ProjectState,
    clip_id: str,
    start_frame: int,
    end_frame: int,
    *,
    media,
) -> None:
    """Move an inactive cut boundary and resize the adjacent active clips."""

    item = next(
        (entry for entry in state.inactive_segments if entry.clip_id == clip_id),
        None,
    )
    if item is None:
        raise InvalidTimeError(f"Unknown inactive clip: {clip_id}")
    if start_frame >= end_frame:
        raise InvalidTimeError("Recut end must be after start.")
    if start_frame < 0 or end_frame > media.duration_frames:
        raise InvalidTimeError("Recut exceeds source media.")

    old_start = item.video.source_in_frame
    old_end = item.video.source_out_frame
    ordered = sorted(state.video_segments, key=lambda clip: clip.source_in_frame)
    previous = next(
        (clip for clip in reversed(ordered) if clip.source_out_frame == old_start),
        None,
    )
    following = next(
        (clip for clip in ordered if clip.source_in_frame == old_end),
        None,
    )

    if previous is None and start_frame != old_start:
        raise InvalidTimeError("The inactive segment has no preceding clip to trim.")
    if following is None and end_frame != old_end:
        raise InvalidTimeError("The inactive segment has no following clip to trim.")
    if previous is not None and start_frame < previous.source_in_frame + 1:
        raise InvalidTimeError("Recut would remove the preceding clip.")
    if following is not None and end_frame > following.source_out_frame - 1:
        raise InvalidTimeError("Recut would remove the following clip.")

    timebase = media.timebase()
    media_samples = timebase.seconds_to_samples(
        timebase.frames_to_seconds(media.duration_frames), Rounding.NEAREST
    )
    old_start_sample = timebase.frame_start_sample(old_start)
    old_end_sample = timebase.frame_start_sample(old_end)
    start_sample = timebase.frame_start_sample(start_frame)
    end_sample = min(timebase.frame_start_sample(end_frame), media_samples)

    previous_audio = (
        next(
            (clip for clip in state.audio_segments if clip.clip_id == previous.clip_id),
            None,
        )
        if previous is not None
        else None
    )
    following_audio = (
        next(
            (clip for clip in state.audio_segments if clip.clip_id == following.clip_id),
            None,
        )
        if following is not None
        else None
    )
    new_previous_audio_out = (
        previous_audio.source_out_sample + start_sample - old_start_sample
        if previous_audio is not None
        else None
    )
    new_following_audio_in = (
        following_audio.source_in_sample + end_sample - old_end_sample
        if following_audio is not None
        else None
    )
    if (
        previous_audio is not None
        and new_previous_audio_out is not None
        and new_previous_audio_out <= previous_audio.source_in_sample
    ):
        raise InvalidTimeError("Recut would remove the preceding audio clip.")
    if (
        following_audio is not None
        and new_following_audio_in is not None
        and new_following_audio_in >= following_audio.source_out_sample
    ):
        raise InvalidTimeError("Recut would remove the following audio clip.")

    if previous is not None:
        video_ratio = (previous.timeline_out_frame - previous.timeline_in_frame) / max(
            1, previous.source_out_frame - previous.source_in_frame
        )
        previous.source_out_frame = start_frame
        previous.timeline_out_frame = previous.timeline_in_frame + max(
            1,
            round(
                (previous.source_out_frame - previous.source_in_frame) * video_ratio
            ),
        )
        previous.transition_out = None
        if previous_audio is not None and new_previous_audio_out is not None:
            audio_ratio = (
                previous_audio.timeline_out_sample - previous_audio.timeline_in_sample
            ) / max(1, previous_audio.source_out_sample - previous_audio.source_in_sample)
            previous_audio.source_out_sample = new_previous_audio_out
            previous_audio.timeline_out_sample = previous_audio.timeline_in_sample + max(
                1,
                round(
                    (
                        previous_audio.source_out_sample
                        - previous_audio.source_in_sample
                    )
                    * audio_ratio
                ),
            )

    if following is not None:
        video_ratio = (following.timeline_out_frame - following.timeline_in_frame) / max(
            1, following.source_out_frame - following.source_in_frame
        )
        following.source_in_frame = end_frame
        following.timeline_out_frame = following.timeline_in_frame + max(
            1,
            round(
                (following.source_out_frame - following.source_in_frame) * video_ratio
            ),
        )
        if following_audio is not None and new_following_audio_in is not None:
            audio_ratio = (
                following_audio.timeline_out_sample - following_audio.timeline_in_sample
            ) / max(1, following_audio.source_out_sample - following_audio.source_in_sample)
            following_audio.source_in_sample = new_following_audio_in
            following_audio.timeline_out_sample = following_audio.timeline_in_sample + max(
                1,
                round(
                    (
                        following_audio.source_out_sample
                        - following_audio.source_in_sample
                    )
                    * audio_ratio
                ),
            )

    inactive_start_sample = timebase.frame_start_sample(start_frame)
    inactive_end_sample = min(timebase.frame_start_sample(end_frame), media_samples)
    if inactive_end_sample <= inactive_start_sample:
        raise InvalidTimeError("Recut would leave an empty inactive segment.")
    item.video.source_in_frame = start_frame
    item.video.source_out_frame = end_frame
    item.video.timeline_in_frame = 0
    item.video.timeline_out_frame = end_frame - start_frame
    item.audio.source_in_sample = inactive_start_sample
    item.audio.source_out_sample = inactive_end_sample
    item.audio.timeline_in_sample = 0
    item.audio.timeline_out_sample = inactive_end_sample - inactive_start_sample
    _repack_timeline(state)


def apply_timeline_edit(state: ProjectState, edit: TimelineEdit) -> ProjectState:
    fps = _fps(state)
    media = state.media_info
    assert media is not None
    if edit.action == "deactivate":
        _deactivate_clip(state, edit.clip_id)
        return state
    if edit.action == "activate":
        _activate_clip(state, edit.clip_id)
        return state
    if edit.action == "recut":
        if edit.start_sec is None or edit.end_sec is None:
            raise InvalidTimeError("Recut requires start and end.")
        _recut_inactive(
            state,
            edit.clip_id,
            round(max(0.0, edit.start_sec) * fps),
            round(max(0.0, edit.end_sec) * fps),
            media=media,
        )
        return state
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

    if edit.action == "slip":
        delta_frames = round(edit.delta_sec * fps)
        length = video.source_out_frame - video.source_in_frame
        new_in = video.source_in_frame + delta_frames
        new_out = video.source_out_frame + delta_frames
        if new_in < 0 or new_out > media.duration_frames:
            raise InvalidTimeError("Slip exceeds source media.")
        if new_out - new_in != length:
            raise InvalidTimeError("Slip would change the clip length.")
        video.source_in_frame, video.source_out_frame = new_in, new_out
        if audio is not None:
            delta_samples = round(edit.delta_sec * media.audio_sample_rate)
            audio_length = audio.source_out_sample - audio.source_in_sample
            media_samples = round(
                media.duration_frames * media.audio_sample_rate / max(0.001, fps)
            )
            audio_in = audio.source_in_sample + delta_samples
            audio_out = audio.source_out_sample + delta_samples
            if audio_in < 0 or audio_out > media_samples:
                raise InvalidTimeError("Slip exceeds source audio.")
            if audio_out - audio_in != audio_length:
                raise InvalidTimeError("Slip would change the audio length.")
            audio.source_in_sample, audio.source_out_sample = audio_in, audio_out
        return state

    if edit.action == "slide":
        delta_frames = round(edit.delta_sec * fps)
        if delta_frames == 0:
            return state
        index = state.video_segments.index(video)
        previous = state.video_segments[index - 1] if index > 0 else None
        following = (
            state.video_segments[index + 1]
            if index + 1 < len(state.video_segments)
            else None
        )
        if (
            previous is None
            or previous.timeline_out_frame != video.timeline_in_frame
            or following is None
            or following.timeline_in_frame != video.timeline_out_frame
        ):
            raise InvalidTimeError("Slide needs a contiguous clip on both sides.")
        old_video = video.model_copy(deep=True)
        old_previous = previous.model_copy(deep=True)
        old_following = following.model_copy(deep=True)
        ratio_prev = (previous.source_out_frame - previous.source_in_frame) / max(
            1, previous.timeline_out_frame - previous.timeline_in_frame
        )
        ratio_next = (following.source_out_frame - following.source_in_frame) / max(
            1, following.timeline_out_frame - following.timeline_in_frame
        )
        previous.timeline_out_frame += delta_frames
        previous.source_out_frame += round(delta_frames * ratio_prev)
        following.timeline_in_frame += delta_frames
        following.source_in_frame += round(delta_frames * ratio_next)
        video.timeline_in_frame += delta_frames
        video.timeline_out_frame += delta_frames
        if (
            previous.timeline_out_frame <= previous.timeline_in_frame
            or following.timeline_out_frame <= following.timeline_in_frame
            or previous.source_out_frame > media.duration_frames
            or following.source_in_frame < 0
            or video.timeline_in_frame < 0
        ):
            state.video_segments[index] = old_video
            state.video_segments[index - 1] = old_previous
            state.video_segments[index + 1] = old_following
            raise InvalidTimeError("Slide exceeds the neighboring clips.")
        if audio is not None:
            delta_samples = round(edit.delta_sec * media.audio_sample_rate)
            audio.timeline_in_sample += delta_samples
            audio.timeline_out_sample += delta_samples
        return state

    if edit.action == "duplicate":
        length = video.source_out_frame - video.source_in_frame
        existing = {clip.clip_id for clip in state.video_segments}
        new_id = _new_clip_id(existing, video.clip_id)
        start = video.timeline_out_frame
        frame_shift = video.timeline_out_frame - video.timeline_in_frame
        for clip in state.video_segments:
            if clip.timeline_in_frame >= start:
                clip.timeline_in_frame += frame_shift
                clip.timeline_out_frame += frame_shift
        copy = video.model_copy(
            update={
                "clip_id": new_id,
                "timeline_in_frame": start,
                "timeline_out_frame": start + frame_shift,
                "source_out_frame": video.source_in_frame + length,
                "transition_out": None,
            }
        )
        state.video_segments.append(copy)
        state.video_segments.sort(key=lambda item: item.timeline_in_frame)
        if audio is not None:
            audio_shift = audio.timeline_out_sample - audio.timeline_in_sample
            audio_start = audio.timeline_out_sample
            for clip in state.audio_segments:
                if clip.timeline_in_sample >= audio_start:
                    clip.timeline_in_sample += audio_shift
                    clip.timeline_out_sample += audio_shift
            audio_copy = audio.model_copy(
                update={
                    "clip_id": new_id,
                    "timeline_in_sample": audio_start,
                    "timeline_out_sample": audio_start + audio_shift,
                    "fade_in_samples": 0,
                    "fade_out_samples": 0,
                }
            )
            state.audio_segments.append(audio_copy)
            state.audio_segments.sort(key=lambda item: item.timeline_in_sample)
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
