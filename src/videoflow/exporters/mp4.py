"""Direct FFmpeg render for the main timeline."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.domain.errors import ExportError
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.exporters.common import (
    require_timeline,
    timeline_duration_frames,
    timeline_duration_samples,
)


def _transform_filters(clip: VideoSegment, media: MediaInfo) -> list[str]:
    transform = clip.transform
    filters: list[str] = []
    if transform.keyframes:
        first = transform.keyframes[0]
        last = transform.keyframes[-1]
        duration = max(1, clip.source_out_frame - clip.source_in_frame)
        span = max(1, duration - 1)
        zoom = (
            f"{first.scale:g}+({last.scale:g}-{first.scale:g})"
            f"*(on-1)/{span}"
        )
        filters.append(
            "zoompan="
            f"z='{zoom}':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            f"d=1:s={media.width}x{media.height}:"
            f"fps={media.fps_num}/{media.fps_den}"
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


def _video_filters(clip: VideoSegment, media: MediaInfo) -> list[str]:
    filters = [
        f"trim=start_frame={clip.source_in_frame}:end_frame={clip.source_out_frame}",
        "setpts=PTS-STARTPTS",
        *_transform_filters(clip, media),
        "settb=AVTB",
    ]
    return filters


def _audio_filters(clip: AudioSegment, media: MediaInfo) -> list[str]:
    sample_rate = media.audio_sample_rate
    duration = (clip.source_out_sample - clip.source_in_sample) / sample_rate
    filters = [
        f"atrim=start_sample={clip.source_in_sample}:end_sample={clip.source_out_sample}",
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
    crossfade = any(item is not None and item.type == "crossfade" for item in transitions)
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

    if crossfade:
        current_video = "[v0]"
        current_audio = "[a0]"
        cumulative = video_durations[0]
        for index, transition in enumerate(transitions, start=1):
            if transition is None or transition.type != "crossfade":
                chains.append(
                    f"{current_video}[v{index}]concat=n=2:v=1:a=0[vx{index}]"
                )
                current_video = f"[vx{index}]"
                if transition is None or transition.audio:
                    chains.append(
                        f"{current_audio}[a{index}]acrossfade=d=0.001[ax{index}]"
                    )
                else:
                    chains.append(
                        f"{current_audio}[a{index}]concat=n=2:v=0:a=1[ax{index}]"
                    )
                current_audio = f"[ax{index}]"
                cumulative += video_durations[index]
                continue
            duration = transition.duration_frames / fps
            offset = max(0.0, cumulative - duration)
            chains.append(
                f"{current_video}[v{index}]xfade=transition=fade:duration={duration:.6f}:"
                f"offset={offset:.6f}[vx{index}]"
            )
            current_video = f"[vx{index}]"
            if transition.audio:
                chains.append(
                    f"{current_audio}[a{index}]acrossfade=d={duration:.6f}[ax{index}]"
                )
            else:
                chains.append(
                    f"{current_audio}[a{index}]concat=n=2:v=0:a=1[ax{index}]"
                )
            current_audio = f"[ax{index}]"
            cumulative += video_durations[index] - duration
        return ";".join(chains), current_video, current_audio

    video_inputs = "".join(f"[v{index}]" for index in range(len(video)))
    audio_inputs = "".join(f"[a{index}]" for index in range(len(audio)))
    chains.append(f"{video_inputs}concat=n={len(video)}:v=1:a=0[vout]")
    chains.append(f"{audio_inputs}concat=n={len(audio)}:v=0:a=1[aout]")
    return ";".join(chains), "[vout]", "[aout]"


SEGMENT_THRESHOLD = 16


def _has_crossfade(state: ProjectState) -> bool:
    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    return any(
        clip.transition_out is not None
        and clip.transition_out.type == "crossfade"
        for clip in video[:-1]
    )


def _audio_graph(state: ProjectState, media: MediaInfo) -> str:
    """Render the full audio timeline without a video filter graph."""

    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    audio = sorted(state.audio_segments, key=lambda item: item.timeline_in_sample)
    transitions = [clip.transition_out for clip in video[:-1]]
    fps = media.fps_num / media.fps_den
    chains: list[str] = []
    for index, clip in enumerate(audio):
        filters = _audio_filters(clip, media)
        previous = transitions[index - 1] if index > 0 else None
        current = transitions[index] if index < len(transitions) else None
        if previous is not None and previous.audio and previous.type == "fade_to_black":
            filters.append(f"afade=t=in:st=0:d={previous.duration_frames / fps:.6f}")
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
    inputs = "".join(f"[a{index}]" for index in range(len(audio)))
    chains.append(f"{inputs}concat=n={len(audio)}:v=0:a=1[aout]")
    return ";".join(chains)


def _video_segment_filters(
    state: ProjectState,
    media: MediaInfo,
    index: int,
) -> list[str]:
    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    clip = video[index]
    transitions = [item.transition_out for item in video[:-1]]
    previous = transitions[index - 1] if index > 0 else None
    current = transitions[index] if index < len(transitions) else None
    fps = media.fps_num / media.fps_den
    filters = _video_filters(clip, media)
    duration = (clip.timeline_out_frame - clip.timeline_in_frame) / fps
    if previous is not None and previous.type == "fade_to_black":
        filters.append(f"fade=t=in:st=0:d={previous.duration_frames / fps:.6f}")
    if current is not None and current.type == "fade_to_black":
        start = max(0.0, duration - current.duration_frames / fps)
        filters.append(f"fade=t=out:st={start:.6f}:d={current.duration_frames / fps:.6f}")
    return filters


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
) -> Path:
    media, video_map, audio_map = require_timeline(state)
    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    if len(video) != len(audio_map) or len(video_map) != len(video):
        raise ExportError("Timeline video and audio segments do not match.")
    destination = Path(output_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    renderer = adapter or FFmpegAdapter()
    source = Path(media.source_path).expanduser()
    total = max(1, len(video))
    with tempfile.TemporaryDirectory(
        prefix="videoflow-render-", dir=destination.parent
    ) as tmp:
        directory = Path(tmp)
        segments: list[Path] = []
        for index in range(len(video)):
            segment = directory / f"segment-{index:04d}.mp4"
            filters = _video_segment_filters(state, media, index)
            renderer.render(
                [
                    "-i",
                    str(source),
                    "-filter_complex",
                    f"[0:v]{','.join(filters)}[v]",
                    "-map",
                    "[v]",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    preset,
                    "-crf",
                    str(crf),
                    "-pix_fmt",
                    "yuv420p",
                    "-threads",
                    "2",
                    str(segment),
                ]
            )
            segments.append(segment)
            if progress is not None:
                progress(min(55, int((index + 1) / total * 55)))

        listing = directory / "segments.txt"
        listing.write_text(
            "".join(f"file '{segment.as_posix()}'\n" for segment in segments),
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
        renderer.render(
            [
                "-i",
                str(source),
                "-filter_complex",
                _audio_graph(state, media),
                "-map",
                "[aout]",
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
                "-movflags",
                "+faststart",
                str(combined),
            ]
        )
        has_finishing = (
            bool(audio_filters)
            or bool(video_filters)
            or ass_path is not None
            or bool(state.overlays)
        )
        if not has_finishing:
            shutil.move(str(combined), str(destination))
            if progress is not None:
                progress(100)
            return destination

        frames = max(1, timeline_duration_frames(state))
        samples = max(1, timeline_duration_samples(state))
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
            audio_filters=audio_filters,
            video_filters=video_filters,
            ass_path=ass_path,
            progress=wrapped,
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
) -> Path:
    """Render the validated main timeline to an H.264/AAC MP4."""

    media = state.media_info
    if media is None:
        raise ExportError("Project has no media")
    if len(state.video_segments) > SEGMENT_THRESHOLD and not _has_crossfade(state):
        return _export_mp4_segmented(
            state,
            Path(output_path),
            adapter=adapter,
            crf=crf,
            preset=preset,
            audio_filters=audio_filters,
            video_filters=video_filters,
            ass_path=ass_path,
            progress=progress,
        )
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
