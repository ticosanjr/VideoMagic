"""Acoustic snap, anti-micro-cut merge, and frame quantisation.

The result is a non-destructive plan: source-sample spans plus a crossfade
intent. The timeline step consumes it later.
"""

from __future__ import annotations

import bisect
from typing import Any

from videoflow.application.retake_spans import subtract_spans
from videoflow.application.rms import min_rms_index
from videoflow.application.spans import merge_spans
from videoflow.domain.decupage import (
    Asu,
    DecupageCut,
    DecupageJoin,
    DecupagePlan,
    DecupageSpan,
)
from videoflow.domain.state import MediaInfo


def build_plan(
    media: MediaInfo,
    asus: list[Asu],
    cuts: list[dict[str, Any]],
    *,
    profile: dict[str, Any],
    noise_events: list[dict[str, Any]],
    review_flags: list[dict[str, str]],
    pre_roll_ms: float = 70.0,
    post_roll_ms: float = 110.0,
    start_search_left_ms: float = 100.0,
    start_search_right_ms: float = 20.0,
    end_search_left_ms: float = 20.0,
    end_search_right_ms: float = 130.0,
    min_cut_gap_ms: float = 180.0,
    crossfade_ms: float = 18.0,
    min_clip_ms: float = 120.0,
) -> DecupagePlan:
    """Return a sample-exact plan with padded, quantised active spans."""

    rate = int(media.audio_sample_rate)
    duration = _duration_samples(media)
    source_cuts = [
        (
            int(item.get("start_sample", 0)),
            int(item.get("end_sample", 0)),
        )
        for item in cuts
        if int(item.get("end_sample", 0)) > int(item.get("start_sample", 0))
    ]
    base = merge_spans(
        [
            (item.start_sample, item.end_sample)
            for item in asus
            if item.end_sample > item.start_sample
        ]
    )
    base = subtract_spans(base, source_cuts)
    pre = _samples(rate, pre_roll_ms)
    post = _samples(rate, post_roll_ms)
    noise = _noise_spans(noise_events)
    trim_spans = [
        (
            int(item.get("start_sample", 0)),
            int(item.get("end_sample", 0)),
        )
        for item in cuts
        if str(item.get("reason") or "") in {"decupage_trim", "trim"}
    ]

    starts = [start for start, _end in base] + [start for start, _end in source_cuts]
    ends = [end for _start, end in base] + [end for _start, end in source_cuts]
    ordered_starts = sorted(set(starts))
    ordered_ends = sorted(set(ends))
    snapped: list[tuple[int, int, float | None, bool]] = []
    for start, end in base:
        position = bisect.bisect_right(ordered_ends, start)
        previous = ordered_ends[position - 1] if position else 0
        position = bisect.bisect_left(ordered_starts, end)
        following = (
            ordered_starts[position] if position < len(ordered_starts) else duration
        )
        new_start = _snap_start(
            start,
            end,
            profile,
            noise,
            rate,
            start_search_left_ms,
            start_search_right_ms,
        )
        new_end = _snap_end(
            start,
            end,
            profile,
            noise,
            rate,
            end_search_left_ms,
            end_search_right_ms,
        )
        raw_start = min(new_start, start) - pre
        raw_end = max(new_end, end) + post
        new_start = _pad_start(raw_start, start, noise, duration)
        new_end = _pad_end(raw_end, end, noise, duration)
        clamped = new_start != raw_start or new_end != raw_end
        valley = _valley_db(profile, new_start)
        new_start = max(previous, min(new_start, end - 1))
        new_end = min(following, duration, max(new_end, start + 1))
        if new_end - new_start >= _samples(rate, min_clip_ms):
            snapped.append((new_start, new_end, valley, clamped))
    pair_snaps = merge_spans([(item[0], item[1]) for item in snapped])
    flags_by_start: dict[int, tuple[float | None, bool]] = {}
    for start, _end, valley, clamped in snapped:
        flags_by_start[start] = (valley, clamped)
    merged: list[tuple[int, int]] = []
    gap_limit = _samples(rate, min_cut_gap_ms)
    for start, end in pair_snaps:
        if not merged:
            merged.append((start, end))
            continue
        gap_start, gap_end = merged[-1][1], start
        gap = gap_end - gap_start
        blocked = (
            _overlaps(gap_start, gap_end, noise)
            or _overlaps(gap_start, gap_end, trim_spans)
            or _overlaps(gap_start, gap_end, source_cuts)
        )
        if 0 < gap < gap_limit and not blocked:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))

    timebase = media.timebase()
    active: list[DecupageSpan] = []
    for start, end in merged:
        frames = timebase.expand_samples_to_frames(start, end)
        q_start = timebase.frame_start_sample(frames.start)
        q_end = min(timebase.frame_start_sample(frames.end), duration)
        if q_end <= q_start:
            continue
        valley, clamped = flags_by_start.get(start, (None, False))
        active.append(
            DecupageSpan(
                start_sample=q_start,
                end_sample=q_end,
                start_sec=round(q_start / rate, 3),
                end_sec=round(q_end / rate, 3),
                valley_rms_dbfs=valley,
                pad_clamped_by_noise=clamped,
                pre_roll_ms=pre_roll_ms,
                post_roll_ms=post_roll_ms,
            )
        )
    joins = [
        DecupageJoin(
            at_sample=span.start_sample,
            duration_ms=crossfade_ms,
            curve="equal_power",
        )
        for span in active[1:]
    ]
    planned_cuts = [
        DecupageCut(
            start_sample=int(item.get("start_sample", 0)),
            end_sample=int(item.get("end_sample", 0)),
            reason=str(item.get("reason") or "remove"),
            asu_id=str(item.get("asu_id") or ""),
            needs_broll_or_punch_in=(
                str(item.get("reason") or "") in {"decupage_trim", "trim"}
                or str(item.get("category") or "") in {"RETAKE", "STUTTER"}
            ),
        )
        for item in cuts
    ]
    final_samples = sum(span.end_sample - span.start_sample for span in active)
    metrics = {
        "source_duration_sec": round(duration / rate, 3),
        "final_duration_sec": round(final_samples / rate, 3),
        "removed_sec": round(max(0, duration - final_samples) / rate, 3),
        "reduction_pct": round((1 - final_samples / max(1, duration)) * 100, 3),
        "active_spans": len(active),
        "cuts": len(planned_cuts),
        "joins": len(joins),
        "review_flags": len(review_flags),
        "crossfade_ms": crossfade_ms,
    }
    return DecupagePlan(
        sample_rate=rate,
        fps_num=media.fps_num,
        fps_den=media.fps_den,
        source_duration_samples=duration,
        active_spans=active,
        cuts=planned_cuts,
        joins=joins,
        review_flags=review_flags,
        metrics=metrics,
    )


def report_markdown(plan: DecupagePlan) -> str:
    metrics = plan.metrics
    lines = [
        "# Decupagem — plano acústico",
        "",
        f"- Original: {metrics.get('source_duration_sec', 0)} s",
        f"- Final: {metrics.get('final_duration_sec', 0)} s",
        f"- Redução: {metrics.get('reduction_pct', 0)}%",
        f"- Cortes: {metrics.get('cuts', 0)}",
        f"- Emendas: {metrics.get('joins', 0)}",
        f"- Review flags: {metrics.get('review_flags', 0)}",
        "",
        "## Cortes",
        "",
        "| início | fim | motivo | ASU |",
        "| ---: | ---: | --- | --- |",
    ]
    for cut in plan.cuts:
        lines.append(
            f"| {cut.start_sample / plan.sample_rate:.3f}s | "
            f"{cut.end_sample / plan.sample_rate:.3f}s | {cut.reason} | {cut.asu_id} |"
        )
    if plan.review_flags:
        lines.extend(["", "## Review flags", ""])
        for flag in plan.review_flags:
            lines.append(
                f"- `{flag.get('asu_id', '')}` — {flag.get('category', 'REVIEW')}: "
                f"{flag.get('reason', '')}"
            )
    return "\n".join(lines) + "\n"


def _duration_samples(media: MediaInfo) -> int:
    from videoflow.domain.timebase import Rounding

    timebase = media.timebase()
    return timebase.seconds_to_samples(
        timebase.frames_to_seconds(media.duration_frames),
        Rounding.NEAREST,
    )


def _samples(rate: int, milliseconds: float) -> int:
    return max(0, round(rate * milliseconds / 1000))


def _noise_spans(events: list[dict[str, Any]]) -> list[tuple[int, int]]:
    spans = []
    for item in events:
        if not isinstance(item, dict):
            continue
        if str(item.get("action") or "remove") == "informational":
            continue
        start = int(item.get("start_sample", 0))
        end = int(item.get("end_sample", 0))
        if end > start:
            spans.append((start, end))
    return merge_spans(spans)


def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < right and end > left for left, right in spans)


def _avoid_noise_start(value: int, noise: list[tuple[int, int]], duration: int) -> int:
    for start, end in noise:
        if start <= value < end:
            return min(duration, end)
    return max(0, value)


def _avoid_noise_end(value: int, noise: list[tuple[int, int]], duration: int) -> int:
    for start, end in noise:
        if start < value <= end:
            return max(0, start)
    return min(duration, value)


def _pad_start(
    value: int,
    anchor: int,
    noise: list[tuple[int, int]],
    duration: int,
) -> int:
    for start, end in noise:
        if value < end and anchor > start:
            value = max(value, end)
    return max(0, min(duration, value))


def _pad_end(
    value: int,
    anchor: int,
    noise: list[tuple[int, int]],
    duration: int,
) -> int:
    for start, end in noise:
        if value > start and anchor < end:
            value = min(value, start)
    return max(0, min(duration, value))


def _valley_db(profile: dict[str, Any], sample: int) -> float | None:
    values = profile.get("db") or []
    if not values:
        return None
    hop = max(1, int(profile.get("hop_samples") or 1))
    index = min(len(values) - 1, max(0, sample // hop))
    try:
        return round(float(values[index]), 3)
    except (TypeError, ValueError):
        return None


def _snap_start(
    start: int,
    end: int,
    profile: dict[str, Any],
    noise: list[tuple[int, int]],
    rate: int,
    left_ms: float,
    right_ms: float,
) -> int:
    low = max(0, start - _samples(rate, left_ms))
    high = min(end - 1, start + _samples(rate, right_ms))
    if not profile or high <= low:
        return start
    candidate = min_rms_index(profile, low, high)
    return _avoid_noise_start(candidate, noise, end)


def _snap_end(
    start: int,
    end: int,
    profile: dict[str, Any],
    noise: list[tuple[int, int]],
    rate: int,
    left_ms: float,
    right_ms: float,
) -> int:
    low = max(start + 1, end - _samples(rate, left_ms))
    high = end + _samples(rate, right_ms)
    if not profile or high <= low:
        return end
    candidate = min_rms_index(profile, low, high)
    return _avoid_noise_end(candidate, noise, high)
