"""Segment-cached MP4 export for cut timelines.

Segments are cached per source range. Per-clip fades and overlays are applied
incrementally. Contiguous crossfades are rendered as one bounded group and the
result is cached, so long timelines never need a single graph for every clip.
Any ineligible timeline is reported to the caller, which then runs the full
exporter, so output never changes silently.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from videoflow.domain.errors import ExportError
from videoflow.domain.state import ProjectState
from videoflow.exporters.common import require_timeline

CACHE_VERSION = 2


class NotEligible(Exception):
    """The timeline needs the full exporter."""


def _render_atomic(adapter: Any, command: list[str], target: Path) -> None:
    """Write a cached segment only after FFmpeg succeeds."""

    temporary = target.with_name(f".{target.stem}.{uuid4().hex}.part.mp4")
    try:
        adapter.render([*command, str(temporary)])
        temporary.replace(target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _aligned(state: ProjectState, media, fps: float) -> bool:
    video = sorted(state.video_segments, key=lambda clip: clip.timeline_in_frame)
    audio = {clip.clip_id: clip for clip in state.audio_segments}
    for clip in video:
        a = audio.get(clip.clip_id)
        if a is None:
            return False
        if clip.transform.scale != 1.0 or clip.transform.pos_x != 0.0:
            return False
        if clip.transform.keyframes or clip.transform.type != "none":
            return False
        expected_in = round(clip.source_in_frame / fps * media.audio_sample_rate)
        expected_out = round(clip.source_out_frame / fps * media.audio_sample_rate)
        if abs(a.source_in_sample - expected_in) > media.audio_sample_rate / fps:
            return False
        if abs(a.source_out_sample - expected_out) > media.audio_sample_rate / fps:
            return False
    return True


def _cache_key(path: Path, clip, crf: int, preset: str) -> str:
    stat = path.stat()
    payload = json.dumps(
        {
            "version": CACHE_VERSION,
            "path": str(path.resolve()),
            "size": stat.st_size,
            "mtime": stat.st_mtime_ns,
            "in": clip.source_in_frame,
            "out": clip.source_out_frame,
            "crf": crf,
            "preset": preset,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def _crossfade_groups(video: list[Any]) -> list[list[int]]:
    groups: list[list[int]] = [[0]]
    for index in range(1, len(video)):
        previous = video[index - 1].transition_out
        if previous is not None and previous.type == "crossfade":
            groups[-1].append(index)
        else:
            groups.append([index])
    return groups


def _group_cache_key(segments: list[Path], transitions: list[Any], preset: str, crf: int) -> str:
    payload = json.dumps(
        {
            "version": CACHE_VERSION,
            "segments": [segment.name for segment in segments],
            "transitions": [
                {
                    "type": item.type,
                    "duration": item.duration_frames,
                    "audio": item.audio,
                }
                for item in transitions
            ],
            "preset": preset,
            "crf": crf,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def export_mp4_incremental(
    state: ProjectState,
    output_path: Path,
    *,
    adapter: Any,
    crf: int = 18,
    preset: str = "medium",
    progress: Callable[[int], None] | None = None,
) -> Path:
    media, video_map, audio_map = require_timeline(state)
    video = sorted(state.video_segments, key=lambda clip: clip.timeline_in_frame)
    if len(video) != len(audio_map) or len(video_map) != len(video):
        raise NotEligible("audio mismatch")
    fps = media.fps_num / media.fps_den
    if not _aligned(state, media, fps):
        raise NotEligible("audio not aligned")
    source = Path(media.source_path).expanduser()
    if not source.is_file():
        raise ExportError("Source media is offline")
    destination = Path(output_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    cache_dir = destination.parent / "segments"
    cache_dir.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []
    total = max(1, len(video))
    for index, clip in enumerate(video):
        key = _cache_key(source, clip, crf, preset)
        previous = video[index - 1].transition_out if index > 0 else None
        current = clip.transition_out
        extra = ""
        if previous is not None and previous.type == "fade_to_black":
            extra += f":fadein={previous.duration_frames}"
        if current is not None and current.type == "fade_to_black":
            extra += f":fadeout={current.duration_frames}"
        segment = cache_dir / f"{key}-{extra.strip(':') or 'plain'}.mp4"
        if not segment.is_file():
            start = clip.source_in_frame / fps
            duration = (clip.source_out_frame - clip.source_in_frame) / fps
            video_filters: list[str] = []
            audio_filters: list[str] = []
            if previous is not None and previous.type == "fade_to_black":
                seconds = previous.duration_frames / fps
                video_filters.append(f"fade=t=in:st=0:d={seconds:.6f}")
                if previous.audio:
                    audio_filters.append(f"afade=t=in:st=0:d={seconds:.6f}")
            if current is not None and current.type == "fade_to_black":
                seconds = current.duration_frames / fps
                video_filters.append(
                    f"fade=t=out:st={max(0.0, duration - seconds):.6f}:d={seconds:.6f}"
                )
                if current.audio:
                    audio_filters.append(
                        f"afade=t=out:st={max(0.0, duration - seconds):.6f}:d={seconds:.6f}"
                    )
            command = [
                "-ss",
                f"{start:.6f}",
                "-i",
                str(source),
                "-t",
                f"{duration:.6f}",
            ]
            if video_filters:
                command.extend(["-vf", ",".join(video_filters)])
            if audio_filters:
                command.extend(["-af", ",".join(audio_filters)])
            command.extend(
                [
                    "-c:v",
                    "libx264",
                    "-preset",
                    preset,
                    "-crf",
                    str(crf),
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                ]
            )
            _render_atomic(adapter, command, segment)
            if progress is not None:
                _report(progress, index, total, 1000)
        segments.append(segment)
    group_files: list[Path] = []
    for group in _crossfade_groups(video):
        if len(group) == 1:
            group_files.append(segments[group[0]])
            continue
        group_segments = [segments[index] for index in group]
        transitions = [video[index].transition_out for index in group[:-1]]
        key = _group_cache_key(group_segments, transitions, preset, crf)
        group_file = cache_dir / f"group-{key}.mp4"
        if not group_file.is_file():
            inputs: list[str] = []
            for segment in group_segments:
                inputs.extend(["-i", str(segment)])
            chains: list[str] = []
            video_label = "[0:v]"
            audio_label = "[0:a]"
            cumulative = (
                video[group[0]].timeline_out_frame - video[group[0]].timeline_in_frame
            ) / fps
            for offset_index in range(1, len(group)):
                transition = transitions[offset_index - 1]
                seconds = transition.duration_frames / fps
                offset = max(0.0, cumulative - seconds)
                chains.append(
                    f"{video_label}[{offset_index}:v]"
                    f"xfade=transition=fade:duration={seconds:.6f}:"
                    f"offset={offset:.6f}[vx{offset_index}]"
                )
                video_label = f"[vx{offset_index}]"
                if transition.audio:
                    chains.append(
                        f"{audio_label}[{offset_index}:a]"
                        f"acrossfade=d={seconds:.6f}[ax{offset_index}]"
                    )
                else:
                    chains.append(
                        f"{audio_label}[{offset_index}:a]"
                        f"concat=n=2:v=0:a=1[ax{offset_index}]"
                    )
                audio_label = f"[ax{offset_index}]"
                clip = video[group[offset_index]]
                cumulative += (
                    clip.timeline_out_frame - clip.timeline_in_frame
                ) / fps - seconds
            _render_atomic(
                adapter,
                [
                    *inputs,
                    "-filter_complex",
                    ";".join(chains),
                    "-map",
                    video_label,
                    "-map",
                    audio_label,
                    "-c:v",
                    "libx264",
                    "-preset",
                    preset,
                    "-crf",
                    str(crf),
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                ],
                group_file,
            )
        group_files.append(group_file)
    listing = cache_dir / "concat.txt"
    listing.write_text(
        "\n".join(
            "file '" + segment.as_posix().replace("'", "'\\''") + "'"
            for segment in group_files
        )
        + "\n",
        encoding="utf-8",
    )
    temporary = destination.with_name(f".{destination.stem}.concat.mp4")
    try:
        adapter.render(
            [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(temporary),
            ]
        )
        shutil.move(str(temporary), str(destination))
    finally:
        temporary.unlink(missing_ok=True)
    if state.overlays:
        _apply_overlays(state, destination, adapter=adapter, fps=fps)
    if destination.stat().st_size == 0:
        raise ExportError("FFmpeg wrote an empty render")
    if progress is not None:
        progress(100)
    return destination


def _apply_overlays(state: ProjectState, destination: Path, *, adapter: Any, fps: float) -> None:
    inputs: list[str] = []
    chains: list[str] = []
    base = "[0:v]"
    for index, overlay in enumerate(state.overlays, start=1):
        path = Path(overlay.path).expanduser()
        if not path.is_file():
            raise ExportError(f"Overlay is offline: {path}")
        duration = overlay.duration_frames / fps
        if overlay.kind == "image":
            inputs.extend(["-loop", "1", "-t", f"{duration:.6f}", "-i", str(path)])
        else:
            inputs.extend(["-t", f"{duration:.6f}", "-i", str(path)])
        chains.append(
            f"[{index}:v]scale=trunc(iw*{overlay.width_ratio:.4f}/2)*2:-2,"
            f"format=rgba,colorchannelmixer=aa={overlay.opacity:.3f},"
            f"setpts=PTS-STARTPTS+{overlay.start_frame / fps:.6f}/TB[ov{index}]"
        )
        chains.append(
            f"{base}[ov{index}]overlay="
            f"x=(W-w)*{overlay.position_x:.4f}:y=(H-h)*{overlay.position_y:.4f}:"
            f"enable='between(t,{overlay.start_frame / fps:.6f},"
            f"{(overlay.start_frame + overlay.duration_frames) / fps:.6f})'[v{index}]"
        )
        base = f"[v{index}]"
    temporary = destination.with_name(f".{destination.stem}.overlay.mp4")
    adapter.render(
        [
            "-i",
            str(destination),
            *inputs,
            "-filter_complex",
            ";".join(chains),
            "-map",
            base,
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(temporary),
        ]
    )
    shutil.move(str(temporary), str(destination))


def _report(progress: Callable[[int], None] | None, index: int, total: int, frame: int) -> None:
    if progress is None:
        return
    progress(min(99, int((index + min(1.0, frame / 1000)) / total * 100)))
