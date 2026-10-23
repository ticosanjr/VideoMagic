"""Small, validated timeline edits over ProjectState."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from videoflow.domain.errors import InvalidTimeError
from videoflow.domain.state import ProjectState
from videoflow.domain.timebase import Rounding


@dataclass(frozen=True, slots=True)
class TimelineEdit:
    clip_id: str
    action: Literal["trim", "move", "delete"]
    start_sec: float | None = None
    end_sec: float | None = None
    delta_sec: float = 0.0


def apply_timeline_edit(state: ProjectState, edit: TimelineEdit) -> ProjectState:
    media = state.media_info
    if media is None:
        raise InvalidTimeError("Timeline edit requires media info.")
    fps = media.fps_num / media.fps_den
    video = next((clip for clip in state.video_segments if clip.clip_id == edit.clip_id), None)
    if video is None:
        raise InvalidTimeError(f"Unknown clip: {edit.clip_id}")
    audio = next((clip for clip in state.audio_segments if clip.clip_id == edit.clip_id), None)

    if edit.action == "delete":
        state.video_segments = [
            clip for clip in state.video_segments if clip.clip_id != edit.clip_id
        ]
        state.audio_segments = [
            clip for clip in state.audio_segments if clip.clip_id != edit.clip_id
        ]
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
    new_source_in = video.source_in_frame + round((start - video.timeline_in_frame) * source_ratio)
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
