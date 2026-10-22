"""Deterministic timeline construction.

Takes padded speech sample spans and produces frame-quantised video segments plus
sample-aligned audio segments. J/L-cuts move the *audio cut point*, not the audio
relative to its own video, so sync inside every clip is preserved.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from videoflow.domain.config import JlCutsConfig, ZoomsConfig
from videoflow.domain.errors import InvalidTimeError
from videoflow.domain.state import (
    AnchorPoint,
    AudioSegment,
    MediaInfo,
    Transform,
    TransformKeyframe,
    TransformType,
    Transition,
    VideoSegment,
)
from videoflow.domain.timebase import Rounding, Timebase


@dataclass(frozen=True, slots=True)
class TimelineBuildResult:
    video_segments: tuple[VideoSegment, ...]
    audio_segments: tuple[AudioSegment, ...]
    warnings: tuple[str, ...]


@dataclass
class _Clip:
    clip_id: str
    vf_in: int
    vf_out: int
    tf_in: int
    tf_out: int
    as_in: int
    as_out: int
    ts_in: int
    ts_out: int
    orig_as_in: int
    orig_as_out: int


def build_timeline(
    media: MediaInfo,
    kept_spans: Sequence[tuple[int, int]],
    *,
    jl: JlCutsConfig,
    zooms: ZoomsConfig,
    transition_frames: int = 0,
    transition_type: str = "crossfade",
    on_audio_done: Callable[[], None] | None = None,
) -> TimelineBuildResult:
    """Build the editable picture and dialogue tracks.

    ``kept_spans`` are padded speech intervals in source samples. Overlaps are
    merged; spans outside the media are clamped. A span that collapses is a
    failure, not a silent drop.
    """

    timebase = media.timebase()
    media_samples = timebase.seconds_to_samples(
        timebase.frames_to_seconds(media.duration_frames), Rounding.NEAREST
    )
    spans = _normalize_spans(kept_spans, media_samples)
    if not spans:
        raise InvalidTimeError("cannot build a timeline with no kept speech")

    warnings: list[str] = []
    clips: list[_Clip] = []
    timeline_frame_cursor = 0
    timeline_sample_cursor = 0

    for start_sample, end_sample in spans:
        frames = timebase.expand_samples_to_frames(start_sample, end_sample)
        vf_in = min(frames.start, media.duration_frames - 1)
        vf_out = min(frames.end, media.duration_frames)
        as_in = timebase.frame_start_sample(vf_in)
        as_out = min(timebase.frame_start_sample(vf_out), media_samples)
        ts_in = timeline_sample_cursor
        length = as_out - as_in
        clip = _Clip(
            clip_id=f"c{len(clips) + 1}",
            vf_in=vf_in,
            vf_out=vf_out,
            tf_in=timeline_frame_cursor,
            tf_out=timeline_frame_cursor + (vf_out - vf_in),
            as_in=as_in,
            as_out=as_out,
            ts_in=ts_in,
            ts_out=ts_in + length,
            orig_as_in=as_in,
            orig_as_out=as_out,
        )
        clips.append(clip)
        timeline_frame_cursor = clip.tf_out
        timeline_sample_cursor = clip.ts_out

    if not clips:
        raise InvalidTimeError("no kept speech survives frame quantisation")

    if jl.enable_j_cuts and jl.enable_l_cuts:
        warnings.append("both J and L cuts are enabled; J-cut wins at each join")

    _apply_audio_cuts(
        clips,
        timebase,
        jl,
        media_samples=media_samples,
        warnings=warnings,
    )
    if on_audio_done is not None:
        on_audio_done()

    video_segments = [
        _video_segment(clip, index, zooms, warnings) for index, clip in enumerate(clips)
    ]
    audio_segments = tuple(
        _audio_segment(clip, index, len(clips), timebase, jl) for index, clip in enumerate(clips)
    )
    if transition_frames > 0 and len(video_segments) > 1:
        for segment in video_segments[:-1]:
            duration = min(
                max(1, int(transition_frames)),
                max(1, segment.timeline_out_frame - segment.timeline_in_frame - 1),
            )
            segment.transition_out = Transition(
                type=transition_type,  # type: ignore[arg-type]
                duration_frames=duration,
            )

    return TimelineBuildResult(
        video_segments=tuple(video_segments),
        audio_segments=audio_segments,
        warnings=tuple(warnings),
    )


def _normalize_spans(
    spans: Sequence[tuple[int, int]],
    media_samples: int,
) -> list[tuple[int, int]]:
    clipped: list[tuple[int, int]] = []
    for start, end in spans:
        if end < start:
            raise InvalidTimeError("kept span ends before it starts")
        start = max(0, start)
        end = min(media_samples, end)
        if end > start:
            clipped.append((start, end))
    clipped.sort()
    merged: list[tuple[int, int]] = []
    for start, end in clipped:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _apply_audio_cuts(
    clips: list[_Clip],
    timebase: Timebase,
    config: JlCutsConfig,
    *,
    media_samples: int,
    warnings: list[str],
) -> None:
    offset = timebase.milliseconds_to_samples(config.offset_ms)
    skipped = 0
    for index in range(len(clips) - 1):
        left = clips[index]
        right = clips[index + 1]
        gap = right.orig_as_in - left.orig_as_out
        if config.enable_j_cuts:
            applied = _jcut_shift(left, right, offset, gap, config.handle_check)
            if applied is None:
                skipped += 1
                continue
            left.as_out -= applied
            left.ts_out -= applied
            right.as_in -= applied
            right.ts_in -= applied
        elif config.enable_l_cuts:
            applied = _lcut_shift(left, right, offset, gap, media_samples, config.handle_check)
            if applied is None:
                skipped += 1
                continue
            left.as_out += applied
            left.ts_out += applied
            right.as_in += applied
            right.ts_in += applied
    if skipped:
        warnings.append(f"{skipped} join(s) kept a straight cut because the handle was too small")


def _jcut_shift(left: _Clip, right: _Clip, offset: int, gap: int, handle_check: bool) -> int | None:
    available = max(0, min(offset, gap))
    if handle_check and available < offset:
        return None
    if left.as_out - available <= left.as_in:
        return None
    if right.ts_in - available < 0:
        return None
    if right.as_in - available < 0:
        return None
    return available


def _lcut_shift(
    left: _Clip,
    right: _Clip,
    offset: int,
    gap: int,
    media_samples: int,
    handle_check: bool,
) -> int | None:
    available = max(0, min(offset, gap, media_samples - left.orig_as_out))
    if handle_check and available < offset:
        return None
    if right.as_in + available >= right.as_out:
        return None
    if right.ts_in + available >= right.ts_out:
        return None
    return available


def _video_segment(
    clip: _Clip,
    index: int,
    config: ZoomsConfig,
    warnings: list[str],
) -> VideoSegment:
    return VideoSegment(
        clip_id=clip.clip_id,
        source_in_frame=clip.vf_in,
        source_out_frame=clip.vf_out,
        timeline_in_frame=clip.tf_in,
        timeline_out_frame=clip.tf_out,
        transform=_transform(index, config, warnings),
    )


def _audio_segment(
    clip: _Clip,
    index: int,
    total: int,
    timebase: Timebase,
    config: JlCutsConfig,
) -> AudioSegment:
    duration = clip.ts_out - clip.ts_in
    if index == 0:
        fade_in = timebase.milliseconds_to_samples(config.fade_in_ms)
    else:
        fade_in = timebase.milliseconds_to_samples(config.audio_crossfade_ms)
    if index == total - 1:
        fade_out = timebase.milliseconds_to_samples(config.fade_out_ms)
    else:
        fade_out = timebase.milliseconds_to_samples(config.audio_crossfade_ms)
    fade_in = min(fade_in, max(0, duration // 2))
    fade_out = min(fade_out, max(0, duration // 2))
    return AudioSegment(
        clip_id=clip.clip_id,
        source_in_sample=clip.as_in,
        source_out_sample=clip.as_out,
        timeline_in_sample=clip.ts_in,
        timeline_out_sample=clip.ts_out,
        fade_in_samples=fade_in,
        fade_out_samples=fade_out,
        fade_curve=config.fade_curve,
    )


def _transform(index: int, config: ZoomsConfig, warnings: list[str]) -> Transform:
    anchor: AnchorPoint = config.anchor_point
    if anchor == "face_detect":
        anchor = "center"
        warnings.append("face detection is not implemented; using center anchor")
    scale = 1.0
    kind: TransformType = "none"
    if config.mode in ("alternate_cuts", "topic_change") and index % 2 == 1:
        scale = min(config.max_scale, max(config.min_scale, config.punch_in_scale))
        kind = "slow_zoom_in" if config.progressive_zoom else "punch_in"
    if config.mode == "topic_change":
        warnings.append("topic_change uses the alternate-cut cadence until topic markers land")
    pos_x = 0.0
    if config.pan_direction != "none":
        pos_x = 0.0
        if kind == "none":
            kind = "pan"
    keyframes: list[TransformKeyframe] = []
    if kind == "slow_zoom_in" and scale > 1.0:
        keyframes = [
            TransformKeyframe(at=0.0, scale=config.min_scale, curve="smooth"),
            TransformKeyframe(at=1.0, scale=scale, curve="smooth"),
        ]
    return Transform(
        scale=scale,
        pos_x=pos_x,
        pos_y=0.0,
        type=kind,
        anchor=anchor,
        pan_direction=config.pan_direction,
        keyframes=keyframes,
    )
