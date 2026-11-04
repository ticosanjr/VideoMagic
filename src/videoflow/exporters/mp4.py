"""Direct FFmpeg render for the main timeline."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.domain.errors import ExportError
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.exporters.common import (
    require_timeline,
    timeline_duration_frames,
)


def _zoom_expression(keyframes: Sequence[Any], span: int) -> str:
    """Piecewise-linear zoom expression for zoompan's ``on`` counter."""

    points = [(max(0.0, min(1.0, frame.at)), float(frame.scale)) for frame in keyframes]
    points = sorted(points)
    if len(points) <= 2:
        first_at, first_scale = points[0]
        last_at, last_scale = points[-1]
        width = max(1, round((last_at - first_at) * span))
        return (
            f"{first_scale:g}+({last_scale:g}-{first_scale:g})"
            f"*clip((on-{round(first_at * span)})/{width},0,1)"
        )
    expression = f"{points[-1][1]:g}"
    for index in range(len(points) - 2, -1, -1):
        start_at, start_scale = points[index]
        end_at, end_scale = points[index + 1]
        start = round(start_at * span)
        end = round(end_at * span)
        width = max(1, end - start)
        segment = (
            f"{start_scale:g}+({end_scale:g}-{start_scale:g})"
            f"*clip((on-{start})/{width},0,1)"
        )
        expression = f"if(lt(on,{end}),{segment},{expression})"
    return expression


def _transform_filters(clip: VideoSegment, media: MediaInfo) -> list[str]:
    transform = clip.transform
    filters: list[str] = []
    if transform.keyframes:
        duration = max(1, clip.source_out_frame - clip.source_in_frame)
        span = max(1, duration - 1)
        zoom = _zoom_expression(transform.keyframes, span)
        width = max(2, media.width * 2)
        height = max(2, media.height * 2)
        filters.extend(
            [
                f"scale={width}:{height}:flags=lanczos",
                "zoompan="
                f"z='{zoom}':"
                "x='trunc((iw-iw/zoom)/2/2)*2':"
                "y='trunc((ih-ih/zoom)/2/2)*2':"
                f"d=1:s={width}x{height}:"
                f"fps={media.fps_num}/{media.fps_den}",
                f"scale={media.width}:{media.height}:flags=lanczos",
            ]
        )
        return filters
    scale = float(transform.scale)
    if scale > 1.0001:
        width = max(2, round(media.width * scale / 2) * 2)
        height = max(2, round(media.height * scale / 2) * 2)
        filters.append(f"scale={width}:{height}:flags=lanczos")
        max_x = max(0, width - media.width)
        max_y = max(0, height - media.height)
        x = max(0, min(max_x, round(max_x / 2 + float(transform.pos_x) * media.width)))
        y = max(0, min(max_y, round(max_y / 2 + float(transform.pos_y) * media.height)))
        filters.append(f"crop={media.width}:{media.height}:{x}:{y}")
    return filters


def _video_filters(
    clip: VideoSegment, media: MediaInfo, *, offset_frames: int = 0
) -> list[str]:
    start = max(0, clip.source_in_frame - offset_frames)
    end = max(start + 1, clip.source_out_frame - offset_frames)
    filters = [
        f"trim=start_frame={start}:end_frame={end}",
        "setpts=PTS-STARTPTS",
        *_transform_filters(clip, media),
        "settb=AVTB",
    ]
    return filters


def _audio_filters(
    clip: AudioSegment, media: MediaInfo, *, offset_samples: int = 0
) -> list[str]:
    sample_rate = media.audio_sample_rate
    duration = (clip.source_out_sample - clip.source_in_sample) / sample_rate
    start = max(0, clip.source_in_sample - offset_samples)
    end = max(start + 1, clip.source_out_sample - offset_samples)
    filters = [
        f"atrim=start_sample={start}:end_sample={end}",
        "asetpts=PTS-STARTPTS",
    ]
    if clip.fade_in_samples > 0:
        filters.append(f"afade=t=in:st=0:d={clip.fade_in_samples / sample_rate:.6f}")
    if clip.fade_out_samples > 0:
        start = max(0.0, duration - clip.fade_out_samples / sample_rate)
        filters.append(
            f"afade=t=out:st={start:.6f}:d={clip.fade_out_samples / sample_rate:.6f}"
        )
    return filters


def build_filter_graph(state: ProjectState) -> tuple[str, str, str]:
    """Return ``(filter_complex, video_label, audio_label)`` for the timeline."""

    media, _, _ = require_timeline(state)
    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    audio = sorted(state.audio_segments, key=lambda item: item.timeline_in_sample)
    if not video or not audio:
        raise ExportError("Timeline needs both video and audio segments")
    fps = media.fps_num / media.fps_den
    video_durations = [
        (clip.timeline_out_frame - clip.timeline_in_frame) / fps for clip in video
    ]
    transitions = [clip.transition_out for clip in video[:-1]]
    chains: list[str] = []
    for index, clip in enumerate(video):
        filters = _video_filters(clip, media)
        previous = transitions[index - 1] if index > 0 else None
        current = transitions[index] if index < len(transitions) else None
        if previous is not None and previous.type == "fade_to_black":
            filters.append(
                f"fade=t=in:st=0:d={previous.duration_frames / fps:.6f}"
            )
        if current is not None and current.type == "fade_to_black":
            start = max(0.0, video_durations[index] - current.duration_frames / fps)
            filters.append(
                f"fade=t=out:st={start:.6f}:d={current.duration_frames / fps:.6f}"
            )
        chains.append(f"[0:v]{','.join(filters)}[v{index}]")
    for index, clip in enumerate(audio):
        filters = _audio_filters(clip, media)
        previous = transitions[index - 1] if index > 0 else None
        current = transitions[index] if index < len(transitions) else None
        if previous is not None and previous.audio and previous.type == "fade_to_black":
            filters.append(
                f"afade=t=in:st=0:d={previous.duration_frames / fps:.6f}"
            )
        if current is not None and current.audio and current.type == "fade_to_black":
            start = max(
                0.0,
                (clip.timeline_out_sample - clip.timeline_in_sample)
                / media.audio_sample_rate
                - current.duration_frames / fps,
            )
            filters.append(
                f"afade=t=out:st={start:.6f}:d={current.duration_frames / fps:.6f}"
            )
        chains.append(f"[0:a]{','.join(filters)}[a{index}]")

    video_inputs = "".join(f"[v{index}]" for index in range(len(video)))
    audio_inputs = "".join(f"[a{index}]" for index in range(len(audio)))
    chains.append(f"{video_inputs}concat=n={len(video)}:v=1:a=0[vout]")
    chains.append(f"{audio_inputs}concat=n={len(audio)}:v=0:a=1[aout]")
    return ";".join(chains), "[vout]", "[aout]"


SEGMENT_THRESHOLD = 16
PRE_ROLL_SECONDS = 1.0
GROUP_CACHE_VERSION = 2


def _has_crossfade(state: ProjectState) -> bool:
    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    return any(
        clip.transition_out is not None
        and clip.transition_out.type == "crossfade"
        for clip in video[:-1]
    )


def timeline_render_frames(state: ProjectState) -> int:
    """Frames produced after crossfades shorten the packed timeline."""

    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    total = sum(
        clip.timeline_out_frame - clip.timeline_in_frame for clip in video
    )
    for clip in video[:-1]:
        transition = clip.transition_out
        if transition is not None and transition.type == "crossfade":
            total -= transition.duration_frames
    return max(1, total)


def _audio_graph_inputs(
    state: ProjectState, media: MediaInfo, source: Path
) -> tuple[list[str], str]:
    """Render the audio timeline from seeked, independent inputs."""

    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    audio = sorted(state.audio_segments, key=lambda item: item.timeline_in_sample)
    transitions = [clip.transition_out for clip in video[:-1]]
    fps = media.fps_num / media.fps_den
    sample_rate = media.audio_sample_rate
    inputs: list[str] = []
    chains: list[str] = []
    for index, clip in enumerate(audio):
        pre_roll = min(clip.source_in_sample, sample_rate)
        seek_sample = clip.source_in_sample - pre_roll
        inputs.extend(
            ["-ss", f"{seek_sample / sample_rate:.6f}", "-i", str(source)]
        )
        filters = _audio_filters(clip, media, offset_samples=seek_sample)
        previous = transitions[index - 1] if index > 0 else None
        current = transitions[index] if index < len(transitions) else None
        if previous is not None and previous.audio and previous.type == "fade_to_black":
            filters.append(f"afade=t=in:st=0:d={previous.duration_frames / fps:.6f}")
        if current is not None and current.audio and current.type == "fade_to_black":
            start = max(
                0.0,
                (clip.timeline_out_sample - clip.timeline_in_sample)
                / sample_rate
                - current.duration_frames / fps,
            )
            filters.append(
                f"afade=t=out:st={start:.6f}:d={current.duration_frames / fps:.6f}"
            )
        chains.append(f"[{index}:a]{','.join(filters)}[a{index}]")

    current_audio = "[a0]"
    for index, transition in enumerate(transitions, start=1):
        if transition is not None and transition.type == "crossfade":
            duration = transition.duration_frames / fps
            if transition.audio:
                chains.append(
                    f"{current_audio}[a{index}]acrossfade=d={duration:.6f}[ax{index}]"
                )
            else:
                chains.append(
                    f"{current_audio}[a{index}]concat=n=2:v=0:a=1[ax{index}]"
                )
        else:
            chains.append(
                f"{current_audio}[a{index}]concat=n=2:v=0:a=1[ax{index}]"
            )
        current_audio = f"[ax{index}]"
    chains.append(f"{current_audio}anull[aout]")
    return inputs, ";".join(chains)


def _video_groups(video: Sequence[VideoSegment]) -> list[list[int]]:
    groups: list[list[int]] = [[0]]
    for index in range(1, len(video)):
        transition = video[index - 1].transition_out
        if transition is not None and transition.type == "crossfade":
            groups[-1].append(index)
        else:
            groups.append([index])
    return groups


def _concat_line(path: Path) -> str:
    return "file '" + str(path).replace("'", "'\\''") + "'"


def _video_segment_filters(
    state: ProjectState,
    media: MediaInfo,
    index: int,
    *,
    video: Sequence[VideoSegment] | None = None,
    transitions: Sequence[Any] | None = None,
    offset_frames: int = 0,
) -> list[str]:
    clips = list(video) if video is not None else sorted(
        state.video_segments, key=lambda item: item.timeline_in_frame
    )
    clip = clips[index]
    edges = (
        list(transitions)
        if transitions is not None
        else [item.transition_out for item in clips[:-1]]
    )
    previous = edges[index - 1] if index > 0 else None
    current = edges[index] if index < len(edges) else None
    fps = media.fps_num / media.fps_den
    filters = _video_filters(clip, media, offset_frames=offset_frames)
    duration = (clip.timeline_out_frame - clip.timeline_in_frame) / fps
    if previous is not None and previous.type == "fade_to_black":
        filters.append(f"fade=t=in:st=0:d={previous.duration_frames / fps:.6f}")
    if current is not None and current.type == "fade_to_black":
        start = max(0.0, duration - current.duration_frames / fps)
        filters.append(f"fade=t=out:st={start:.6f}:d={current.duration_frames / fps:.6f}")
    return filters


def _group_key(
    state: ProjectState,
    media: MediaInfo,
    group: Sequence[int],
    *,
    source: Path,
    crf: int,
    preset: str,
    scale_height: int | None,
) -> str:
    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    stat = source.stat()
    payload = {
        "version": GROUP_CACHE_VERSION,
        "source": [str(source.resolve()), stat.st_size, stat.st_mtime_ns],
        "fps": [media.fps_num, media.fps_den],
        "crf": crf,
        "preset": preset,
        "scale_height": scale_height,
        "clips": [video[index].model_dump(mode="json") for index in group],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]


def _render_video_group(
    state: ProjectState,
    media: MediaInfo,
    group: Sequence[int],
    *,
    renderer: Any,
    source: Path,
    cache_dir: Path,
    crf: int,
    preset: str,
    scale_height: int | None = None,
) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _group_key(
        state,
        media,
        group,
        source=source,
        crf=crf,
        preset=preset,
        scale_height=scale_height,
    )
    cached = cache_dir / f"group-{key}.mp4"
    if cached.is_file() and cached.stat().st_size > 0:
        return cached
    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    transitions = [item.transition_out for item in video[:-1]]
    fps = media.fps_num / media.fps_den
    inputs: list[str] = []
    chains: list[str] = []
    durations: list[float] = []
    for slot, clip_index in enumerate(group):
        clip = video[clip_index]
        pre_roll = min(
            clip.source_in_frame, max(1, int(round(fps * PRE_ROLL_SECONDS)))
        )
        seek_frame = clip.source_in_frame - pre_roll
        inputs.extend(["-ss", f"{seek_frame / fps:.6f}", "-i", str(source)])
        filters = _video_segment_filters(
            state,
            media,
            clip_index,
            video=video,
            transitions=transitions,
            offset_frames=seek_frame,
        )
        chains.append(f"[{slot}:v]{','.join(filters)}[c{slot}]")
        durations.append(
            (clip.timeline_out_frame - clip.timeline_in_frame) / fps
        )

    label = "[c0]"
    if len(group) > 1:
        cumulative = durations[0]
        for offset_index in range(1, len(group)):
            transition = video[group[offset_index - 1]].transition_out
            if transition is None or transition.type != "crossfade":
                raise ExportError("Crossfade group has a non-crossfade transition")
            seconds = transition.duration_frames / fps
            offset = max(0.0, cumulative - seconds)
            chains.append(
                f"{label}[c{offset_index}]xfade=transition=fade:"
                f"duration={seconds:.6f}:offset={offset:.6f}[x{offset_index}]"
            )
            label = f"[x{offset_index}]"
            cumulative += durations[offset_index] - seconds

    if scale_height is not None:
        height = max(64, min(2160, int(scale_height)))
        chains.append(f"{label}scale=-2:{height}:flags=lanczos[vout]")
        label = "[vout]"

    target = cache_dir / f"group-{key}.mp4"
    temporary = target.with_name(f".{target.stem}.{uuid4().hex}.part.mp4")
    try:
        renderer.render(
            [
                *inputs,
                "-filter_complex",
                ";".join(chains),
                "-map",
                label,
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                preset,
                "-crf",
                str(crf),
                "-pix_fmt",
                "yuv420p",
                "-r",
                f"{media.fps_num}/{media.fps_den}",
                "-movflags",
                "+faststart",
                str(temporary),
            ]
        )
        temporary.replace(target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return target


def _export_mp4_segmented(
    state: ProjectState,
    output_path: Path,
    *,
    adapter: Any,
    crf: int,
    preset: str,
    audio_filters: Sequence[str] | None,
    video_filters: Sequence[str] | None,
    ass_path: Path | None,
    progress: Callable[[int], None] | None,
    scale_height: int | None = None,
    cache_dir: Path | None = None,
) -> Path:
    media, video_map, audio_map = require_timeline(state)
    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    if len(video) != len(audio_map) or len(video_map) != len(video):
        raise ExportError("Timeline video and audio segments do not match.")
    destination = Path(output_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    renderer = adapter or FFmpegAdapter()
    source = Path(media.source_path).expanduser()
    segments_dir = (
        Path(cache_dir).expanduser()
        if cache_dir is not None
        else destination.parent / "segments"
    )
    groups = _video_groups(video)
    total_groups = max(1, len(groups))
    with tempfile.TemporaryDirectory(
        prefix="videoflow-render-", dir=destination.parent
    ) as tmp:
        directory = Path(tmp)
        group_files: list[Path] = []
        for group_index, group in enumerate(groups):
            group_files.append(
                _render_video_group(
                    state,
                    media,
                    group,
                    renderer=renderer,
                    source=source,
                    cache_dir=segments_dir,
                    crf=crf,
                    preset=preset,
                    scale_height=scale_height,
                )
            )
            if progress is not None:
                progress(min(55, int((group_index + 1) / total_groups * 55)))

        listing = directory / "segments.txt"
        listing.write_text(
            "".join(f"{_concat_line(path)}\n" for path in group_files),
            encoding="utf-8",
        )
        video_only = directory / "video.mp4"
        renderer.render(
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
                str(video_only),
            ]
        )
        if progress is not None:
            progress(58)

        audio_only = directory / "audio.m4a"
        audio_inputs, audio_graph = _audio_graph_inputs(state, media, source)
        audio_label = "[aout]"
        audio_effects = [item for item in (audio_filters or []) if item]
        if audio_effects:
            audio_graph += f";{audio_label}{','.join(audio_effects)}[afinal]"
            audio_label = "[afinal]"
        renderer.render(
            [
                *audio_inputs,
                "-filter_complex",
                audio_graph,
                "-map",
                audio_label,
                "-vn",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(audio_only),
            ]
        )
        if progress is not None:
            progress(60)

        combined = directory / "combined.mp4"
        renderer.render(
            [
                "-i",
                str(video_only),
                "-i",
                str(audio_only),
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c",
                "copy",
                "-shortest",
                "-movflags",
                "+faststart",
                str(combined),
            ]
        )
        has_video_finishing = (
            bool(video_filters)
            or ass_path is not None
            or bool(state.overlays)
        )
        if not has_video_finishing:
            shutil.move(str(combined), str(destination))
            if progress is not None:
                progress(100)
            return destination

        frames = timeline_render_frames(state)
        samples = max(
            1, int(round(frames / (media.fps_num / media.fps_den) * media.audio_sample_rate))
        )
        final_media = media.model_copy(
            update={"source_path": str(combined), "duration_frames": frames}
        )
        synthetic = ProjectState(
            media_info=final_media,
            video_segments=[
                VideoSegment(
                    clip_id="render",
                    source_in_frame=0,
                    source_out_frame=frames,
                    timeline_in_frame=0,
                    timeline_out_frame=frames,
                )
            ],
            audio_segments=[
                AudioSegment(
                    clip_id="render",
                    source_in_sample=0,
                    source_out_sample=samples,
                    timeline_in_sample=0,
                    timeline_out_sample=samples,
                )
            ],
            overlays=list(state.overlays),
        )
        def wrapped(value: int) -> None:
            if progress is not None:
                progress(min(100, 60 + int(max(0, min(100, value)) * 0.4)))

        return export_mp4(
            synthetic,
            destination,
            adapter=renderer,
            crf=crf,
            preset=preset,
            audio_filters=None,
            video_filters=video_filters,
            ass_path=ass_path,
            progress=wrapped,
            scale_height=None,
        )


def _filter_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def export_mp4(
    state: ProjectState,
    output_path: Path,
    *,
    adapter: Any | None = None,
    crf: int = 18,
    preset: str = "medium",
    audio_filters: Sequence[str] | None = None,
    video_filters: Sequence[str] | None = None,
    ass_path: Path | None = None,
    progress: Callable[[int], None] | None = None,
    scale_height: int | None = None,
    cache_dir: Path | None = None,
) -> Path:
    """Render the validated main timeline to an H.264/AAC MP4 atomically."""

    media = state.media_info
    if media is None:
        raise ExportError("Project has no media")
    destination = Path(output_path).expanduser()
    if len(state.video_segments) > SEGMENT_THRESHOLD or _has_crossfade(state):
        return _export_mp4_segmented(
            state,
            destination,
            adapter=adapter,
            crf=crf,
            preset=preset,
            audio_filters=audio_filters,
            video_filters=video_filters,
            ass_path=ass_path,
            progress=progress,
            scale_height=scale_height,
            cache_dir=cache_dir,
        )
    temporary = destination.with_name(
        f".{destination.stem}.{uuid4().hex}.part.mp4"
    )
    try:
        _render_classic_mp4(
            state,
            temporary,
            adapter=adapter,
            crf=crf,
            preset=preset,
            audio_filters=audio_filters,
            video_filters=video_filters,
            ass_path=ass_path,
            progress=progress,
            scale_height=scale_height,
        )
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def _render_classic_mp4(
    state: ProjectState,
    output_path: Path,
    *,
    adapter: Any | None = None,
    crf: int = 18,
    preset: str = "medium",
    audio_filters: Sequence[str] | None = None,
    video_filters: Sequence[str] | None = None,
    ass_path: Path | None = None,
    progress: Callable[[int], None] | None = None,
    scale_height: int | None = None,
) -> Path:
    """Render the classic single-pass graph to ``output_path``."""

    media = state.media_info
    if media is None:
        raise ExportError("Project has no media")
    graph, video_label, audio_label = build_filter_graph(state)
    filters = [item for item in (audio_filters or []) if item]
    if filters:
        graph += f";{audio_label}{','.join(filters)}[amaster]"
        audio_label = "[amaster]"
    color_filters = [item for item in (video_filters or []) if item]
    if color_filters:
        graph += f";{video_label}{','.join(color_filters)}[vcolor]"
        video_label = "[vcolor]"
    if ass_path is not None:
        graph += f";{video_label}ass='{_filter_path(Path(ass_path))}'[vtitle]"
        video_label = "[vtitle]"
    fps = media.fps_num / media.fps_den
    overlay_inputs: list[str] = []
    overlay_chains: list[str] = []
    input_index = 1
    for index, overlay in enumerate(state.overlays):
        path = Path(overlay.path).expanduser()
        if not path.is_file():
            continue
        duration = overlay.duration_frames / fps
        if overlay.kind == "image":
            overlay_inputs.extend(["-loop", "1", "-t", f"{duration:.6f}", "-i", str(path)])
        else:
            overlay_inputs.extend(
                ["-stream_loop", "-1", "-t", f"{duration:.6f}", "-i", str(path)]
            )
        overlay_chains.append(
            f"[{input_index}:v]scale=trunc(iw*{overlay.width_ratio:.4f}/2)*2:-2,"
            f"format=rgba,colorchannelmixer=aa={overlay.opacity:.3f},"
            f"setpts=PTS-STARTPTS[ov{index}]"
        )
        start = overlay.start_frame / fps
        end = start + duration
        overlay_chains.append(
            f"{video_label}[ov{index}]overlay="
            f"x=(W-w)*{overlay.position_x:.4f}:y=(H-h)*{overlay.position_y:.4f}:"
            f"enable='between(t,{start:.6f},{end:.6f})'[vov{index}]"
        )
        video_label = f"[vov{index}]"
        input_index += 1
    if overlay_chains:
        graph += ";" + ";".join(overlay_chains)
    if scale_height is not None:
        height = max(64, min(2160, int(scale_height)))
        graph += f";{video_label}scale=-2:{height}:flags=lanczos[vscale]"
        video_label = "[vscale]"
    destination = Path(output_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    renderer = adapter or FFmpegAdapter()
    total_frames = max(1, timeline_duration_frames(state))

    def frame_progress(frame: int) -> None:
        if progress is not None:
            progress(min(99, max(1, int(frame / total_frames * 100))))

    command = [
            "-i",
            str(Path(media.source_path).expanduser()),
            *overlay_inputs,
            "-filter_complex",
            graph,
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
            "-shortest",
            str(destination),
        ]
    if progress is not None:
        renderer.render(command, progress=frame_progress)
    else:
        renderer.render(command)
    if not destination.is_file():
        raise ExportError(f"FFmpeg did not write {destination.name}")
    return destination
