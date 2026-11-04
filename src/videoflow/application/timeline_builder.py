"""Deterministic timeline construction.

Takes padded speech sample spans and produces frame-quantised video segments plus
sample-aligned audio segments. J/L-cuts move the *audio cut point*, not the audio
relative to its own video, so sync inside every clip is preserved.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from videoflow.domain.config import JlCutsConfig, ZoomsConfig
from videoflow.domain.errors import InvalidTimeError
from videoflow.domain.state import (
    AnchorPoint,
    AudioSegment,
    InactiveReason,
    InactiveSegment,
    InactiveSpan,
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


_WATERMARK = re.compile(
    r"legendas?\s+pela\s+comunidade|amara\.org|subtitles?\s+by|"
    r"legendado\s+por|transcri(?:ção|cao)\s+por",
    re.IGNORECASE,
)


def detect_noise_spans(
    speech: Sequence[tuple[int, int]],
    transcript: Sequence[Any],
    *,
    sample_rate: int,
    mode: str = "non_speech",
    min_ms: int = 180,
    confidence: float = 0.5,
) -> list[InactiveSpan]:
    """Detect VAD intervals that contain no speech words.

    ``non_speech`` removes intervals with no transcript words at all (coughs,
    throat clearing, breaths). ``non_speech_and_nonlexical`` also removes
    ellipsis-only and subtitle-watermark intervals. The aggressive mode is
    opt-in because some creators keep quiet room tone or music beds.
    """

    if mode == "off" or not transcript:
        return []
    minimum = max(1, (min_ms * sample_rate + 500) // 1000)
    words: list[tuple[int, int, str, float]] = []
    for sentence in transcript:
        for word in getattr(sentence, "words", []):
            words.append(
                (word.start_sample, word.end_sample, word.word, float(word.probability))
            )
    spans: list[InactiveSpan] = []
    for start, end in speech:
        if end - start < minimum:
            continue
        inside = [item for item in words if item[1] > start and item[0] < end]
        sentence_text = " ".join(
            item.text
            for item in transcript
            if item.end_sample > start and item.start_sample < end
        )
        watermark = bool(_WATERMARK.search(sentence_text))
        lexical = [
            item for item in inside if re.search(r"[A-Za-zÀ-ÿ0-9]", item[2])
        ]
        if not inside:
            if (
                sentence_text
                and re.search(r"[A-Za-zÀ-ÿ0-9]", sentence_text)
                and not watermark
            ):
                continue
            spans.append(InactiveSpan(start_sample=start, end_sample=end, reason="noise"))
            continue
        if not lexical and not watermark:
            spans.append(InactiveSpan(start_sample=start, end_sample=end, reason="noise"))
            continue
        if mode != "non_speech_and_nonlexical":
            continue
        average = sum(item[3] for item in inside) / max(1, len(inside))
        nonlexical = all(
            not re.search(r"[A-Za-zÀ-ÿ0-9]", item[2]) for item in inside
        )
        if watermark or (average < confidence and nonlexical):
            spans.append(InactiveSpan(start_sample=start, end_sample=end, reason="noise"))
    return spans


def _keep_internal_gap(
    start: int,
    end: int,
    *,
    mode: str,
    rms_at: Callable[[int, int], int] | None,
    energy_threshold: int,
    long_gap_ms: int,
    sample_rate: int,
) -> bool:
    """Decide whether a no-word gap is possible untranscribed speech."""

    if mode == "all":
        return False
    energy = rms_at(start, end) if rms_at is not None else 0
    if mode == "silence":
        return energy >= energy_threshold
    long_gap = (long_gap_ms * sample_rate + 500) // 1000
    # Smart: short gaps are breaths, coughs, or pauses and are removed. Only a
    # long gap with speech-like energy may be untranscribed speech worth keeping.
    return end - start >= long_gap and energy >= energy_threshold


_STANDALONE_WORDS = {
    "sim",
    "não",
    "nao",
    "talvez",
    "certo",
    "ok",
    "obrigado",
    "obrigada",
    "até",
    "ate",
    "tchau",
}


def transcript_spans(
    transcript: Sequence[Any],
    discard_ids: set[int],
    *,
    sample_rate: int,
    duration_samples: int,
    pad_before_ms: int = 20,
    pad_after_ms: int = 40,
    noise_mode: str = "non_speech",
    noise_confidence: float = 0.5,
    min_ms: int = 80,
    max_internal_gap_ms: int = 150,
    internal_gap_mode: str = "smart",
    gap_energy_threshold: int = 800,
    long_gap_ms: int = 800,
    drop_isolated_words: bool = True,
    rms_at: Callable[[int, int], int] | None = None,
    kept_gaps: list[tuple[int, int]] | None = None,
    forced_cuts: Sequence[tuple[int, int]] = (),
) -> tuple[list[tuple[int, int]], list[InactiveSpan]]:
    """Build tight word-run spans from complete transcript sentences.

    Each sentence is split at gaps above ``max_internal_gap_ms``. The gap is
    removed unless the smart mode decides it is long and speech-like enough to
    be untranscribed speech. This removes internal dead air, coughs, and the
    aborted occurrence of a repeated phrase while keeping the final take.
    """

    maximum_gap = max(1, (max_internal_gap_ms * sample_rate + 500) // 1000)
    before = max(0, (pad_before_ms * sample_rate + 500) // 1000)
    after = max(0, (pad_after_ms * sample_rate + 500) // 1000)
    minimum = max(1, (min_ms * sample_rate + 500) // 1000)
    runs: list[tuple[int, int, int, str]] = []
    noise: list[InactiveSpan] = []
    for sentence in transcript:
        if sentence.id in discard_ids:
            continue
        start_bound = max(0, min(duration_samples, sentence.start_sample))
        end_bound = max(start_bound, min(duration_samples, sentence.end_sample))
        if end_bound <= start_bound:
            continue
        text = sentence.text.strip()
        lexical = [
            word for word in sentence.words if re.search(r"[A-Za-zÀ-ÿ0-9]", word.word)
        ]
        watermark = bool(_WATERMARK.search(text))
        only_punctuation = bool(text) and not re.search(r"[A-Za-zÀ-ÿ0-9]", text)
        remove = watermark or not lexical or only_punctuation
        if (
            not remove
            and noise_mode == "non_speech_and_nonlexical"
            and sentence.words
        ):
            average = sum(word.probability for word in sentence.words) / len(
                sentence.words
            )
            remove = average < noise_confidence and only_punctuation
        if remove:
            noise.append(
                InactiveSpan(
                    start_sample=start_bound,
                    end_sample=end_bound,
                    reason="noise",
                )
            )
            continue

        words = sorted(sentence.words, key=lambda word: word.start_sample)
        words = [
            word
            for word in words
            if not any(
                start <= (word.start_sample + word.end_sample) // 2 <= end
                for start, end in forced_cuts
            )
        ]
        if not words:
            continue
        sentence_runs: list[tuple[int, int, int, str]] = []
        current: list[Any] = [words[0]]
        for previous, word in zip(words, words[1:], strict=False):
            gap_start = max(previous.end_sample, start_bound)
            gap_end = min(word.start_sample, end_bound)
            gap = word.start_sample - previous.end_sample
            if gap <= maximum_gap:
                current.append(word)
                continue
            forced = any(
                max(gap_start, cut_start) < min(gap_end, cut_end)
                for cut_start, cut_end in forced_cuts
            )
            if not forced and _keep_internal_gap(
                max(0, gap_start),
                max(gap_start, gap_end),
                mode=internal_gap_mode,
                rms_at=rms_at,
                energy_threshold=gap_energy_threshold,
                long_gap_ms=long_gap_ms,
                sample_rate=sample_rate,
            ):
                if kept_gaps is not None:
                    kept_gaps.append((max(0, gap_start), max(gap_start, gap_end)))
                current.append(word)
            else:
                sentence_runs.append(
                    (
                        current[0].start_sample,
                        current[-1].end_sample,
                        len(current),
                        current[0].word,
                    )
                )
                current = [word]
        sentence_runs.append(
            (
                current[0].start_sample,
                current[-1].end_sample,
                len(current),
                current[0].word,
            )
        )
        has_main_run = any(count >= 2 for _start, _end, count, _word in sentence_runs)
        for run in sentence_runs:
            start, end, count, first_word = run
            if (
                drop_isolated_words
                and has_main_run
                and len(sentence_runs) > 1
                and count == 1
            ):
                token = re.sub(r"[^\wÀ-ÿ]+", "", first_word.casefold())
                if token not in _STANDALONE_WORDS:
                    noise.append(
                        InactiveSpan(
                            start_sample=max(0, start),
                            end_sample=max(start + 1, end),
                            reason="noise",
                        )
                    )
                    continue
            runs.append(run)

    runs.sort(key=lambda item: (item[0], item[1]))
    merged: list[tuple[int, int]] = []
    for start, end, _count, _word in runs:
        start = max(0, min(duration_samples, start))
        end = max(start, min(duration_samples, end))
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    spans: list[tuple[int, int]] = []
    for index, (start, end) in enumerate(merged):
        padded_start = max(0, start - before)
        padded_end = min(duration_samples, end + after)
        if index > 0:
            previous_end = merged[index - 1][1]
            midpoint = (previous_end + start) // 2
            padded_start = max(padded_start, midpoint)
        if index + 1 < len(merged):
            next_start = merged[index + 1][0]
            midpoint = (end + next_start) // 2
            padded_end = min(padded_end, midpoint)
        if padded_end - padded_start < minimum:
            if padded_end > padded_start:
                noise.append(
                    InactiveSpan(
                        start_sample=padded_start,
                        end_sample=padded_end,
                        reason="noise",
                    )
                )
            continue
        spans.append((padded_start, padded_end))
    return spans, noise


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


def build_inactive_segments(
    media: MediaInfo,
    active_video: Sequence[VideoSegment],
    *,
    silence_spans: Sequence[InactiveSpan] = (),
    retake_spans: Sequence[InactiveSpan] = (),
    noise_spans: Sequence[InactiveSpan] = (),
) -> tuple[InactiveSegment, ...]:
    """Turn the gaps between active source ranges into Recut segments.

    Boundaries come from the quantised active video ranges, so the inactive
    pieces never overlap the rendered timeline. Reasons are attributed by
    source-time overlap, with manual decisions outranking silence and retakes.
    """

    timebase = media.timebase()
    media_samples = timebase.seconds_to_samples(
        timebase.frames_to_seconds(media.duration_frames), Rounding.NEAREST
    )
    active = _normalize_spans(
        [(segment.source_in_frame, segment.source_out_frame) for segment in active_video],
        media.duration_frames,
    )
    gaps: list[tuple[int, int]] = []
    cursor = 0
    for start, end in active:
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < media.duration_frames:
        gaps.append((cursor, media.duration_frames))

    segments: list[InactiveSegment] = []
    for index, (start_frame, end_frame) in enumerate(gaps, start=1):
        start_sample = timebase.frame_start_sample(start_frame)
        end_sample = min(timebase.frame_start_sample(end_frame), media_samples)
        if end_sample <= start_sample:
            continue
        clip_id = f"i{index}"
        length_frames = end_frame - start_frame
        length_samples = end_sample - start_sample
        reason = _inactive_reason(
            start_sample,
            end_sample,
            silence_spans=silence_spans,
            retake_spans=retake_spans,
            noise_spans=noise_spans,
        )
        segments.append(
            InactiveSegment(
                clip_id=clip_id,
                video=VideoSegment(
                    clip_id=clip_id,
                    source_in_frame=start_frame,
                    source_out_frame=end_frame,
                    timeline_in_frame=0,
                    timeline_out_frame=length_frames,
                ),
                audio=AudioSegment(
                    clip_id=clip_id,
                    source_in_sample=start_sample,
                    source_out_sample=end_sample,
                    timeline_in_sample=0,
                    timeline_out_sample=length_samples,
                ),
                reason=reason,
            )
        )
    return tuple(segments)


def _inactive_reason(
    start: int,
    end: int,
    *,
    silence_spans: Sequence[InactiveSpan],
    retake_spans: Sequence[InactiveSpan],
    noise_spans: Sequence[InactiveSpan] = (),
) -> InactiveReason:
    overlaps = {"manual": 0, "retake": 0, "noise": 0, "silence": 0}
    for span in (*retake_spans, *noise_spans, *silence_spans):
        overlap = min(end, span.end_sample) - max(start, span.start_sample)
        if overlap > 0:
            overlaps[span.reason] = max(overlaps[span.reason], overlap)
    if overlaps["manual"]:
        return "manual"
    if overlaps["retake"]:
        return "retake"
    if overlaps["noise"]:
        return "noise"
    if overlaps["silence"]:
        return "silence"
    return "silence"


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
