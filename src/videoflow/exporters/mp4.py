"""Direct FFmpeg render for the main timeline."""

from __future__ import annotations

import functools
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.disk import ensure_free_space_for_export
from videoflow.application.fonts import fonts_dir
from videoflow.application.media_integrity import validate_integrity
from videoflow.core.media_contract import (
    MediaContractError,
    assert_audio_duration,
    channel_rms,
    needs_mono_repair,
)
from videoflow.domain.errors import ExportError
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.exporters.common import (
    require_timeline,
    timeline_duration_samples,
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
        segment = f"{start_scale:g}+({end_scale:g}-{start_scale:g})*clip((on-{start})/{width},0,1)"
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
                "setsar=1",
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
    filters.append("setsar=1")
    return filters


def _video_filters(clip: VideoSegment, media: MediaInfo, *, offset_frames: int = 0) -> list[str]:
    start = max(0, clip.source_in_frame - offset_frames)
    end = max(start + 1, clip.source_out_frame - offset_frames)
    filters = [
        f"trim=start_frame={start}:end_frame={end}",
        "setpts=PTS-STARTPTS",
        *_transform_filters(clip, media),
        "setsar=1",
        "settb=AVTB",
    ]
    return filters


def _audio_filters(
    clip: AudioSegment,
    media: MediaInfo,
    *,
    offset_samples: int = 0,
    sample_rate: int | None = None,
    mono_repair: str = "",
) -> list[str]:
    clip_rate = int(sample_rate or media.audio_sample_rate)
    duration = (clip.source_out_sample - clip.source_in_sample) / clip_rate
    start = max(0, clip.source_in_sample - offset_samples)
    end = max(start + 1, clip.source_out_sample - offset_samples)
    filters = [
        f"atrim=start_sample={start}:end_sample={end}",
        "asetpts=PTS-STARTPTS",
    ]
    if clip.fade_in_samples > 0:
        filters.append(f"afade=t=in:st=0:d={clip.fade_in_samples / clip_rate:.6f}")
    if clip.fade_out_samples > 0:
        start = max(0.0, duration - clip.fade_out_samples / clip_rate)
        filters.append(f"afade=t=out:st={start:.6f}:d={clip.fade_out_samples / clip_rate:.6f}")
    if mono_repair == "left":
        filters.append("pan=stereo|c0=c0|c1=c0")
    elif mono_repair == "right":
        filters.append("pan=stereo|c0=c1|c1=c1")
    filters.extend(
        [
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo",
            "aresample=48000",
        ]
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
    video_durations = [(clip.timeline_out_frame - clip.timeline_in_frame) / fps for clip in video]
    transitions = [clip.transition_out for clip in video[:-1]]
    chains: list[str] = []
    mono_repair = needs_mono_repair(*channel_rms(Path(media.source_path).expanduser()))
    for index, clip in enumerate(video):
        filters = _video_filters(clip, media)
        previous = transitions[index - 1] if index > 0 else None
        current = transitions[index] if index < len(transitions) else None
        if previous is not None and previous.type == "fade_to_black":
            filters.append(f"fade=t=in:st=0:d={previous.duration_frames / fps:.6f}")
        if current is not None and current.type == "fade_to_black":
            start = max(0.0, video_durations[index] - current.duration_frames / fps)
            filters.append(f"fade=t=out:st={start:.6f}:d={current.duration_frames / fps:.6f}")
        chains.append(f"[0:v]{','.join(filters)}[v{index}]")
    for index, clip in enumerate(audio):
        filters = _audio_filters(clip, media, mono_repair=mono_repair)
        previous = transitions[index - 1] if index > 0 else None
        current = transitions[index] if index < len(transitions) else None
        if previous is not None and previous.audio and previous.type == "fade_to_black":
            filters.append(f"afade=t=in:st=0:d={previous.duration_frames / fps:.6f}")
        if current is not None and current.audio and current.type == "fade_to_black":
            start = max(
                0.0,
                (clip.timeline_out_sample - clip.timeline_in_sample) / media.audio_sample_rate
                - current.duration_frames / fps,
            )
            filters.append(f"afade=t=out:st={start:.6f}:d={current.duration_frames / fps:.6f}")
        chains.append(f"[0:a]{','.join(filters)}[a{index}]")

    video_inputs = "".join(f"[v{index}]" for index in range(len(video)))
    audio_inputs = "".join(f"[a{index}]" for index in range(len(audio)))
    chains.append(f"{video_inputs}concat=n={len(video)}:v=1:a=0[vout]")
    chains.append(f"{audio_inputs}concat=n={len(audio)}:v=0:a=1[aout]")
    return ";".join(chains), "[vout]", "[aout]"


SEGMENT_THRESHOLD = 16
PRE_ROLL_SECONDS = 1.0
GROUP_CACHE_VERSION = "4.0"
DEFAULT_EXPORT_FPS = 30

YOUTUBE_PROFILE = "youtube_h264"
DEFAULT_AUDIO_BITRATE = "192k"
YOUTUBE_AUDIO_BITRATE = "320k"
YOUTUBE_LUFS = -15.5
YOUTUBE_TRUE_PEAK_DB = -1.5


@functools.lru_cache(maxsize=1)
def video_encoder() -> str:
    """Return ``libx264`` or ``h264_nvenc`` after proving NVENC works."""

    from videoflow.core.nvenc import nvenc_available as _nvenc_works

    requested = os.environ.get("VF_VIDEO_ENCODER", "auto").strip().lower()
    if requested in {"libx264", "x264", "cpu"}:
        return "libx264"
    if requested in {"nvenc", "h264_nvenc"}:
        return "h264_nvenc"
    if requested not in {"auto", ""}:
        return "libx264"
    if shutil.which("nvidia-smi") is None:
        return "libx264"
    try:
        probe = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        if probe.returncode != 0 or not probe.stdout.strip():
            return "libx264"
        return (
            "h264_nvenc"
            if _nvenc_works(shutil.which("ffmpeg") or "ffmpeg")
            else "libx264"
        )
    except (OSError, subprocess.SubprocessError):
        return "libx264"


def output_render_frames(state: ProjectState, fps: int | None = None) -> int:
    """Frame count at the delivery fps, preserving the timeline duration."""

    media = state.media_info
    if media is None:
        return 0
    if not fps or fps <= 0:
        return timeline_render_frames(state)
    if not media.fps_num:
        return timeline_render_frames(state)
    source_fps = media.fps_num / media.fps_den
    seconds = timeline_render_frames(state) / source_fps
    return max(1, int(round(seconds * fps)))


def _video_encode_args(
    *,
    crf: int,
    preset: str,
    profile: str,
    fps_num: int,
    fps_den: int,
    cfr: bool,
) -> list[str]:
    """Return the H.264 encoder flags shared by both render paths."""

    encoder = video_encoder()
    if encoder == "h264_nvenc":
        from videoflow.core.nvenc import DEFAULT_ARGS, nvenc_args

        proven = nvenc_args(shutil.which("ffmpeg") or "ffmpeg")
        if proven == list(DEFAULT_ARGS):
            proven = [
                "-preset",
                "p4",
                "-rc",
                "vbr",
                "-cq",
                str(crf),
                "-b:v",
                "0",
            ]
        args = ["-c:v", "h264_nvenc", *proven, "-pix_fmt", "yuv420p"]
    else:
        args = [
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
        ]
    if profile == YOUTUBE_PROFILE and encoder == "libx264":
        args.extend(["-profile:v", "high", "-level", "4.1"])
    if cfr:
        args.extend(["-fps_mode", "cfr", "-r", f"{fps_num}/{fps_den}"])
    return args


def _audio_encode_args(*, bitrate: str) -> list[str]:
    return ["-c:a", "aac", "-b:a", bitrate]


def loudnorm_filter(loudness_lufs: float, true_peak_db: float = YOUTUBE_TRUE_PEAK_DB) -> str:
    """Return the single-pass EBU R128 target used by the social master."""

    return f"loudnorm=I={loudness_lufs:g}:TP={true_peak_db:g}:LRA=9"


def _is_multi_source(state: ProjectState) -> bool:
    source_ids = {(clip.source_id or state.primary_source_id) for clip in state.video_segments}
    source_ids.update((clip.source_id or state.primary_source_id) for clip in state.audio_segments)
    return len({item for item in source_ids if item}) > 1


XFADE_TRANSITIONS: dict[str, str] = {
    "crossfade": "fade",
    "wipe_left": "wipeleft",
    "wipe_right": "wiperight",
    "slide_up": "slideup",
    "zoom_in": "zoomin",
    "whip_pan": "slideleft",
    "glitch": "pixelize",
}


def _is_xfade(transition: Any | None) -> bool:
    return transition is not None and transition.type in XFADE_TRANSITIONS


def _has_crossfade(state: ProjectState) -> bool:
    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    return any(_is_xfade(clip.transition_out) for clip in video[:-1])


def timeline_render_frames(state: ProjectState) -> int:
    """Frames produced after crossfades shorten the packed timeline."""

    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    total = sum(clip.timeline_out_frame - clip.timeline_in_frame for clip in video)
    for clip in video[:-1]:
        transition = clip.transition_out
        if _is_xfade(transition):
            total -= transition.duration_frames
    return max(1, total)


def _validate_delivery(path: Path, adapter: Any | None = None) -> None:
    if not _duration_gate_enabled(adapter):
        return
    from videoflow.adapters.ffmpeg import FFmpegAdapter

    if adapter is not None and not isinstance(adapter, FFmpegAdapter):
        return
    from videoflow.core.media_contract import validate_media

    report = validate_media(path, "deliverable")
    if not report.ok:
        first = (
            report.errors[0]
            if report.errors
            else {"code": "media_contract", "message": "invalid"}
        )
        raise ExportError(
            f"{path.name} violated the media contract: "
            f"{first.get('code')}: {first.get('message')}"
        )


def _duration_gate_enabled(adapter: Any | None) -> bool:
    """Fakes used in unit tests do not write decodable MP4 files."""

    return adapter is None or isinstance(adapter, FFmpegAdapter)


def _expected_seconds(state: ProjectState) -> float:
    media = state.media_info
    if media is None:
        return 0.0
    fps = media.fps_num / media.fps_den
    return timeline_render_frames(state) / fps if fps else 0.0


def _last_sentence_end_sec(state: ProjectState) -> float | None:
    from videoflow.application.time_map import last_speech_timeline_sec

    return last_speech_timeline_sec(state)


def _integrity_report(
    state: ProjectState,
    path: Path,
    *,
    fps_override: int | None = None,
):
    media = state.media_info
    source_fps = (
        (media.fps_num / media.fps_den) if media is not None and media.fps_den else 0.0
    )
    fps = float(fps_override) if fps_override else source_fps
    return validate_integrity(
        path,
        _expected_seconds(state),
        expected_frames=output_render_frames(state, fps_override),
        expected_samples=timeline_duration_samples(state) if state.audio_segments else 0,
        fps=fps,
        last_sentence_end_sec=_last_sentence_end_sec(state),
    )


def _write_export_layout(state: ProjectState, destination: Path) -> None:
    media = state.media_info
    if media is None:
        return
    from videoflow.application.overlay_geometry import caption_box, write_layout

    style = state.modules_config.shorts.caption_style
    caption = caption_box(style, media.width, media.height)
    write_layout(state, destination.parent, media.width, media.height, caption=caption)


def _audio_graph_inputs(
    state: ProjectState, media: MediaInfo, source: Path
) -> tuple[list[str], str]:
    """Render the audio timeline from seeked, independent inputs."""

    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    audio = sorted(state.audio_segments, key=lambda item: item.timeline_in_sample)
    transitions = [clip.transition_out for clip in video[:-1]]
    fps = media.fps_num / media.fps_den
    sample_rate = media.audio_sample_rate
    mono_repair = needs_mono_repair(*channel_rms(Path(media.source_path).expanduser()))
    inputs: list[str] = []
    chains: list[str] = []
    for index, clip in enumerate(audio):
        clip_media = state.audio_media(clip) or media
        clip_rate = clip_media.audio_sample_rate
        pre_roll = min(clip.source_in_sample, clip_rate)
        seek_sample = clip.source_in_sample - pre_roll
        inputs.extend(
            [
                "-ss",
                f"{seek_sample / clip_rate:.6f}",
                "-i",
                str(Path(clip_media.source_path).expanduser()),
            ]
        )
        filters = _audio_filters(
            clip,
            media,
            offset_samples=seek_sample,
            sample_rate=clip_rate,
            mono_repair=mono_repair,
        )
        previous = transitions[index - 1] if index > 0 else None
        current = transitions[index] if index < len(transitions) else None
        if previous is not None and previous.audio and previous.type == "fade_to_black":
            filters.append(f"afade=t=in:st=0:d={previous.duration_frames / fps:.6f}")
        if current is not None and current.audio and current.type == "fade_to_black":
            start = max(
                0.0,
                (clip.timeline_out_sample - clip.timeline_in_sample) / sample_rate
                - current.duration_frames / fps,
            )
            filters.append(f"afade=t=out:st={start:.6f}:d={current.duration_frames / fps:.6f}")
        chains.append(f"[{index}:a]{','.join(filters)}[a{index}]")

    current_audio = "[a0]"
    for index, transition in enumerate(transitions, start=1):
        if transition is not None and transition.type == "crossfade":
            duration = transition.duration_frames / fps
            if transition.audio:
                chains.append(f"{current_audio}[a{index}]acrossfade=d={duration:.6f}[ax{index}]")
            else:
                chains.append(f"{current_audio}[a{index}]concat=n=2:v=0:a=1[ax{index}]")
        else:
            chains.append(f"{current_audio}[a{index}]concat=n=2:v=0:a=1[ax{index}]")
        current_audio = f"[ax{index}]"
    chains.append(f"{current_audio}anull[aout]")
    return inputs, ";".join(chains)


def export_timeline_audio(
    state: ProjectState,
    output_path: Path,
    *,
    adapter: Any | None = None,
    audio_filters: Sequence[str] | None = None,
    sample_rate: int | None = None,
    progress: Callable[[int], None] | None = None,
) -> Path:
    """Render only the active timeline audio to a WAV master.

    The filter graph is the same one used by the MP4 exporter, so cuts,
    trims, fades, crossfades, and multi-source offsets match the picture.
    """

    media, _, _ = require_timeline(state)
    if not state.audio_segments:
        raise ExportError("Timeline has no audio segments")
    inputs, graph = _audio_graph_inputs(state, media, Path(media.source_path).expanduser())
    chain = ",".join(item for item in (audio_filters or ()) if item)
    label = "[aout]"
    if chain:
        graph += f";{label}{chain}[amaster]"
        label = "[amaster]"
    destination = Path(output_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.stem}.part.wav")
    command = [
        *inputs,
        "-filter_complex",
        graph,
        "-map",
        label,
        "-vn",
        "-ar",
        str(int(sample_rate or 48_000)),
        "-ac",
        "2",
        "-c:a",
        "pcm_s24le",
        str(temporary),
    ]
    renderer = adapter or FFmpegAdapter()
    try:
        renderer.render(command)
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    expected = timeline_duration_samples(state) / float(sample_rate or media.audio_sample_rate)
    tolerance = max(1.0 / 30.0, (media.fps_den / media.fps_num) if media.fps_den else 0.0)
    if isinstance(renderer, FFmpegAdapter):
        try:
            assert_audio_duration(destination, expected, tolerance_sec=tolerance)
        except MediaContractError as exc:
            raise ExportError(str(exc.message)) from exc
    if progress is not None:
        progress(100)
    return destination


def _video_groups(
    video: Sequence[VideoSegment],
    *,
    max_block: int = 12,
) -> list[list[int]]:
    """Group xfades separately and pack contiguous hard cuts into macro-blocks."""

    if not video:
        return []
    groups: list[list[int]] = [[0]]
    for index in range(1, len(video)):
        previous = video[index - 1]
        current = video[index]
        transition = previous.transition_out
        group = groups[-1]
        has_xfade = any(_is_xfade(video[item].transition_out) for item in group[:-1])
        same_source = (previous.source_id or "") == (current.source_id or "")
        same_transform = previous.transform == current.transform
        if _is_xfade(transition):
            if has_xfade:
                group.append(index)
                continue
            if group and group[-1] == index - 1:
                group.pop()
            groups.append([index - 1, index])
            continue
        if not has_xfade and same_source and same_transform and len(group) < max_block:
            group.append(index)
        else:
            groups.append([index])
    return [group for group in groups if group]


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
    clips = (
        list(video)
        if video is not None
        else sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
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
    profile: str,
    scale_height: int | None,
    fps: int | None = None,
) -> str:
    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    source_signatures = []
    for index in group:
        clip_media = state.video_media(video[index]) or media
        clip_path = Path(clip_media.source_path).expanduser()
        stat = clip_path.stat()
        source_signatures.append([str(clip_path.resolve()), stat.st_size, stat.st_mtime_ns])
    payload = {
        "version": GROUP_CACHE_VERSION,
        "sources": source_signatures,
        "fps": [media.fps_num, media.fps_den],
        "output_fps": fps or 0,
        "crf": crf,
        "preset": preset,
        "profile": profile,
        "scale_height": scale_height,
        "clips": [video[index].model_dump(mode="json") for index in group],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]


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
    profile: str = "",
    scale_height: int | None = None,
    fps: int | None = None,
) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _group_key(
        state,
        media,
        group,
        source=source,
        crf=crf,
        preset=preset,
        profile=profile,
        scale_height=scale_height,
        fps=fps,
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
        pre_roll = min(clip.source_in_frame, max(1, int(round(fps * PRE_ROLL_SECONDS))))
        seek_frame = clip.source_in_frame - pre_roll
        clip_media = state.video_media(clip) or media
        clip_fps = clip_media.fps_num / clip_media.fps_den
        inputs.extend(
            [
                "-ss",
                f"{seek_frame / clip_fps:.6f}",
                "-i",
                str(Path(clip_media.source_path).expanduser()),
            ]
        )
        filters = _video_segment_filters(
            state,
            media,
            clip_index,
            video=video,
            transitions=transitions,
            offset_frames=seek_frame,
        )
        chains.append(f"[{slot}:v]{','.join(filters)}[c{slot}]")
        durations.append((clip.timeline_out_frame - clip.timeline_in_frame) / fps)

    label = "[c0]"
    if len(group) > 1:
        transitions = [video[group[offset - 1]].transition_out for offset in range(1, len(group))]
        if any(_is_xfade(item) for item in transitions):
            cumulative = durations[0]
            for offset_index in range(1, len(group)):
                transition = video[group[offset_index - 1]].transition_out
                if not _is_xfade(transition):
                    raise ExportError("Transition group has a non-xfade transition")
                seconds = transition.duration_frames / fps
                offset = max(0.0, cumulative - seconds)
                effect = XFADE_TRANSITIONS.get(transition.type, "fade") if transition else "fade"
                chains.append(
                    f"{label}[c{offset_index}]xfade=transition={effect}:"
                    f"duration={seconds:.6f}:offset={offset:.6f}[x{offset_index}]"
                )
                label = f"[x{offset_index}]"
                cumulative += durations[offset_index] - seconds
        else:
            chain_inputs = "".join(f"[c{index}]" for index in range(len(group)))
            chains.append(f"{chain_inputs}concat=n={len(group)}:v=1:a=0[vgroup]")
            label = "[vgroup]"

    if scale_height is not None:
        height = max(64, min(2160, int(scale_height)))
        chains.append(f"{label}scale=-2:{height}:flags=lanczos,setsar=1[vout]")
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
                *_video_encode_args(
                    crf=crf,
                    preset=preset,
                    profile=profile,
                    fps_num=fps or media.fps_num,
                    fps_den=1 if fps else media.fps_den,
                    cfr=True,
                ),
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
    profile: str = "",
    audio_bitrate: str = DEFAULT_AUDIO_BITRATE,
    loudness_lufs: float | None = None,
    true_peak_db: float = YOUTUBE_TRUE_PEAK_DB,
    cfr: bool = False,
    audio_master: Path | None = None,
    audio_filters: Sequence[str] | None = None,
    video_filters: Sequence[str] | None = None,
    ass_path: Path | None = None,
    progress: Callable[[int], None] | None = None,
    scale_height: int | None = None,
    cache_dir: Path | None = None,
    fps: int | None = None,
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
        Path(cache_dir).expanduser() if cache_dir is not None else destination.parent / "segments"
    )
    groups = _video_groups(video)
    total_groups = max(1, len(groups))
    with tempfile.TemporaryDirectory(prefix="videoflow-render-", dir=destination.parent) as tmp:
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
                    profile=profile,
                    scale_height=scale_height,
                    fps=fps,
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
        master_file = Path(audio_master).expanduser() if audio_master is not None else None
        if master_file is not None and not master_file.is_file():
            master_file = None
        if master_file is not None:
            renderer.render(
                [
                    "-i",
                    str(master_file),
                    "-vn",
                    "-af",
                    "aresample=async=1:first_pts=0,apad",
                    *_audio_encode_args(bitrate=audio_bitrate),
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                    "-t",
                    f"{_expected_seconds(state):.6f}",
                    "-movflags",
                    "+faststart",
                    str(audio_only),
                ]
            )
        else:
            audio_inputs, audio_graph = _audio_graph_inputs(state, media, source)
            audio_label = "[aout]"
            audio_effects = [item for item in (audio_filters or []) if item]
            audio_effects.append(f"apad=whole_dur={_expected_seconds(state):.6f}")
            if loudness_lufs is not None:
                audio_effects.append(loudnorm_filter(loudness_lufs, true_peak_db))
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
                    *_audio_encode_args(bitrate=audio_bitrate),
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                    "-t",
                    f"{_expected_seconds(state):.6f}",
                    str(audio_only),
                ]
            )
        if progress is not None:
            progress(60)

        combined = directory / "combined.mp4"
        expected = _expected_seconds(state)
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
                "-t",
                f"{expected:.6f}",
                "-movflags",
                "+faststart",
                str(combined),
            ]
        )
        report = (
            _integrity_report(state, combined, fps_override=fps)
            if _duration_gate_enabled(adapter)
            else None
        )
        if report is not None and not report.ok:
            repaired = directory / "combined-cfr.mp4"
            renderer.render(
                [
                    "-i",
                    str(video_only),
                    "-i",
                    str(audio_only),
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
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
                    audio_bitrate,
                    "-fps_mode",
                    "cfr",
                    "-r",
                    f"{fps or media.fps_num}/{1 if fps else media.fps_den}",
                    "-af",
                    "aresample=async=1,apad",
                    "-t",
                    f"{expected:.6f}",
                    "-movflags",
                    "+faststart",
                    str(repaired),
                ]
            )
            report = _integrity_report(state, repaired, fps_override=fps)
            if not report.ok:
                raise ExportError(
                    f"{destination.name} failed the duration gate after CFR repair: {report.reason}"
                )
            combined = repaired
        has_video_finishing = bool(video_filters) or ass_path is not None or bool(state.overlays)
        if not has_video_finishing:
            shutil.move(str(combined), str(destination))
            _write_export_layout(state, destination)
            _validate_delivery(destination, adapter)
            if progress is not None:
                progress(100)
            return destination

        output_fps = float(fps) if fps else media.fps_num / media.fps_den
        frames = output_render_frames(state, fps)
        samples = max(
            1, int(round(frames / output_fps * media.audio_sample_rate))
        )
        final_media = media.model_copy(
            update={
                "source_path": str(combined),
                "duration_frames": frames,
                "fps_num": fps or media.fps_num,
                "fps_den": 1 if fps else media.fps_den,
            }
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
            profile=profile,
            audio_bitrate=audio_bitrate,
            loudness_lufs=None,
            true_peak_db=true_peak_db,
            cfr=cfr,
            audio_master=None,
            audio_filters=None,
            video_filters=video_filters,
            ass_path=ass_path,
            progress=wrapped,
            scale_height=None,
            fps=fps,
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
    profile: str = "",
    audio_bitrate: str = DEFAULT_AUDIO_BITRATE,
    loudness_lufs: float | None = None,
    true_peak_db: float = YOUTUBE_TRUE_PEAK_DB,
    cfr: bool = False,
    audio_master: Path | None = None,
    audio_filters: Sequence[str] | None = None,
    video_filters: Sequence[str] | None = None,
    ass_path: Path | None = None,
    progress: Callable[[int], None] | None = None,
    scale_height: int | None = None,
    cache_dir: Path | None = None,
    fps: int | None = None,
) -> Path:
    """Render the validated main timeline to an H.264/AAC MP4 atomically."""

    media = state.media_info
    if media is None:
        raise ExportError("Project has no media")
    destination = Path(output_path).expanduser()
    ensure_free_space_for_export(destination.parent, state)
    if (
        len(state.video_segments) > SEGMENT_THRESHOLD
        or _has_crossfade(state)
        or _is_multi_source(state)
    ):
        return _export_mp4_segmented(
            state,
            destination,
            adapter=adapter,
            crf=crf,
            preset=preset,
            profile=profile,
            audio_bitrate=audio_bitrate,
            loudness_lufs=loudness_lufs,
            true_peak_db=true_peak_db,
            cfr=cfr,
            audio_master=audio_master,
            audio_filters=audio_filters,
            video_filters=video_filters,
            ass_path=ass_path,
            progress=progress,
            scale_height=scale_height,
            cache_dir=cache_dir,
            fps=fps,
        )
    temporary = destination.with_name(f".{destination.stem}.{uuid4().hex}.part.mp4")
    try:
        _render_classic_mp4(
            state,
            temporary,
            adapter=adapter,
            crf=crf,
            preset=preset,
            profile=profile,
            audio_bitrate=audio_bitrate,
            loudness_lufs=loudness_lufs,
            true_peak_db=true_peak_db,
            cfr=cfr,
            audio_master=audio_master,
            audio_filters=audio_filters,
            video_filters=video_filters,
            ass_path=ass_path,
            progress=progress,
            scale_height=scale_height,
            fps=fps,
        )
        report = (
            _integrity_report(state, temporary, fps_override=fps)
            if _duration_gate_enabled(adapter)
            else None
        )
        if report is not None and not report.ok:
            temporary.unlink(missing_ok=True)
            _render_classic_mp4(
                state,
                temporary,
                adapter=adapter,
                crf=crf,
                preset=preset,
                profile=profile,
                audio_bitrate=audio_bitrate,
                loudness_lufs=loudness_lufs,
                true_peak_db=true_peak_db,
                cfr=True,
                audio_master=audio_master,
                audio_filters=audio_filters,
                video_filters=video_filters,
                ass_path=ass_path,
                progress=progress,
                scale_height=scale_height,
                fps=fps,
            )
            report = (
                _integrity_report(state, temporary, fps_override=fps)
                if _duration_gate_enabled(adapter)
                else None
            )
        if report is not None and not report.ok:
            raise ExportError(f"{destination.name} failed the duration gate: {report.reason}")
        temporary.replace(destination)
        _write_export_layout(state, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    _validate_delivery(destination, adapter)
    return destination


def _render_classic_mp4(
    state: ProjectState,
    output_path: Path,
    *,
    adapter: Any | None = None,
    crf: int = 18,
    preset: str = "medium",
    profile: str = "",
    audio_bitrate: str = DEFAULT_AUDIO_BITRATE,
    loudness_lufs: float | None = None,
    true_peak_db: float = YOUTUBE_TRUE_PEAK_DB,
    cfr: bool = False,
    audio_master: Path | None = None,
    audio_filters: Sequence[str] | None = None,
    video_filters: Sequence[str] | None = None,
    ass_path: Path | None = None,
    progress: Callable[[int], None] | None = None,
    scale_height: int | None = None,
    fps: int | None = None,
) -> Path:
    """Render the classic single-pass graph to ``output_path``."""

    media = state.media_info
    if media is None:
        raise ExportError("Project has no media")
    graph, video_label, audio_label = build_filter_graph(state)
    master_file = Path(audio_master).expanduser() if audio_master is not None else None
    if master_file is not None and not master_file.is_file():
        master_file = None
    filters = [item for item in (audio_filters or []) if item]
    if loudness_lufs is not None and master_file is None:
        filters.append(loudnorm_filter(loudness_lufs, true_peak_db))
    if filters and master_file is None:
        graph += f";{audio_label}{','.join(filters)}[amaster]"
        audio_label = "[amaster]"
    elif master_file is not None:
        # The mastered WAV replaces the timeline audio; consume the graph output
        # so FFmpeg does not reject the unconnected concat result.
        graph += f";{audio_label}anullsink"
    color_filters = [item for item in (video_filters or []) if item]
    if color_filters:
        graph += f";{video_label}{','.join(color_filters)}[vcolor]"
        video_label = "[vcolor]"
    source_fps = media.fps_num / media.fps_den
    overlay_inputs: list[str] = []
    input_index = 2 if master_file is not None else 1

    def apply_overlays(overlays: Sequence[Any]) -> None:
        nonlocal video_label, input_index
        from videoflow.application.overlay_geometry import overlay_box

        for overlay in sorted(overlays, key=lambda item: (item.z, item.start_frame)):
            path = Path(overlay.path).expanduser()
            if not path.is_file():
                continue
            duration = overlay.duration_frames / source_fps
            if overlay.kind == "image":
                overlay_inputs.extend(
                    ["-loop", "1", "-t", f"{duration:.6f}", "-i", str(path)]
                )
            elif path.suffix.casefold() == ".webm":
                # FFmpeg's native VP9 decoder drops alpha; force libvpx-vp9.
                overlay_inputs.extend(
                    [
                        "-c:v",
                        "libvpx-vp9",
                        "-stream_loop",
                        "-1",
                        "-t",
                        f"{duration:.6f}",
                        "-i",
                        str(path),
                    ]
                )
            else:
                overlay_inputs.extend(
                    ["-stream_loop", "-1", "-t", f"{duration:.6f}", "-i", str(path)]
                )
            overlay_filters: list[str] = []
            if overlay.transformative_crop:
                overlay_filters.append("crop=trunc(iw*0.9/2)*2:trunc(ih*0.9/2)*2")
            overlay_filters.append(f"scale=trunc(iw*{overlay.width_ratio:.4f}/2)*2:-2")
            if overlay.ken_burns:
                overlay_filters.append(
                    "zoompan=z='min(zoom+0.0004,1.08)':d=1:"
                    "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                )
            overlay_filters.extend(
                ["format=rgba", f"colorchannelmixer=aa={overlay.opacity:.3f}"]
            )
            fade_seconds = max(0.0, overlay.transition_frames / source_fps)
            if fade_seconds > 0 and overlay.transition_in in {"fade", "crossfade"}:
                overlay_filters.append(
                    f"fade=t=in:st=0:d={min(fade_seconds, duration):.6f}:alpha=1"
                )
            if fade_seconds > 0 and overlay.transition_out in {"fade", "crossfade"}:
                overlay_filters.append(
                    f"fade=t=out:st={max(0.0, duration - fade_seconds):.6f}:"
                    f"d={min(fade_seconds, duration):.6f}:alpha=1"
                )
            overlay_filters.append("setpts=PTS-STARTPTS")
            label = f"ov{input_index}"
            overlay_chains = [
                f"[{input_index}:v]{','.join(overlay_filters)}[{label}]"
            ]
            box = overlay_box(overlay, media.width, media.height)
            x = max(0, min(max(0, media.width - box.width), box.x))
            y = max(0, min(max(0, media.height - box.height), box.y))
            start = overlay.start_frame / source_fps
            end = start + duration
            overlay_chains.append(
                f"{video_label}[{label}]overlay="
                f"x={x}:y={y}:"
                f"enable='between(t,{start:.6f},{end:.6f})'[v{label}]"
            )
            graph_segments.append(";".join(overlay_chains))
            video_label = f"[v{label}]"
            input_index += 1

    graph_segments: list[str] = []
    apply_overlays([overlay for overlay in state.overlays if overlay.z < 40])
    if ass_path is not None:
        ass_filter = f"ass='{_filter_path(Path(ass_path))}'"
        ass_filter += f":fontsdir='{_filter_path(fonts_dir())}'"
        graph_segments.append(f"{video_label}{ass_filter}[vtitle]")
        video_label = "[vtitle]"
    apply_overlays([overlay for overlay in state.overlays if overlay.z >= 40])
    if graph_segments:
        graph += ";" + ";".join(graph_segments)
    if scale_height is not None:
        height = max(64, min(2160, int(scale_height)))
        graph += f";{video_label}scale=-2:{height}:flags=lanczos,setsar=1[vscale]"
        video_label = "[vscale]"
    destination = Path(output_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    renderer = adapter or FFmpegAdapter()
    total_frames = max(1, output_render_frames(state, fps))

    def frame_progress(frame: int) -> None:
        if progress is not None:
            progress(min(99, max(1, int(frame / total_frames * 100))))

    command = [
        "-i",
        str(Path(media.source_path).expanduser()),
        *(["-i", str(master_file)] if master_file is not None else []),
        *overlay_inputs,
        "-filter_complex",
        graph,
        "-map",
        video_label,
        "-map",
        "1:a" if master_file is not None else audio_label,
        *_video_encode_args(
            crf=crf,
            preset=preset,
            profile=profile,
            fps_num=fps or media.fps_num,
            fps_den=1 if fps else media.fps_den,
            cfr=cfr or bool(fps),
        ),
        *_audio_encode_args(bitrate=audio_bitrate),
        "-ar",
        "48000",
        "-ac",
        "2",
        "-t",
        f"{_expected_seconds(state):.6f}",
        "-movflags",
        "+faststart",
        str(destination),
    ]
    if progress is not None:
        renderer.render(command, progress=frame_progress)
    else:
        renderer.render(command)
    if not destination.is_file():
        raise ExportError(f"FFmpeg did not write {destination.name}")
    _validate_delivery(destination, adapter)
    return destination
