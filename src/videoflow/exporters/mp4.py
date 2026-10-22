"""Direct FFmpeg render for the main timeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.domain.errors import ExportError
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.exporters.common import require_timeline


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


def _video_chain(clip: VideoSegment, media: MediaInfo, index: int) -> str:
    filters = [
        f"trim=start_frame={clip.source_in_frame}:end_frame={clip.source_out_frame}",
        "setpts=PTS-STARTPTS",
        *_transform_filters(clip, media),
    ]
    return f"[0:v]{','.join(filters)}[v{index}]"


def _audio_chain(clip: AudioSegment, media: MediaInfo, index: int) -> str:
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
    return f"[0:a]{','.join(filters)}[a{index}]"


def build_filter_graph(state: ProjectState) -> tuple[str, str, str]:
    """Return ``(filter_complex, video_label, audio_label)`` for the timeline."""

    media, _, _ = require_timeline(state)
    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    audio = sorted(state.audio_segments, key=lambda item: item.timeline_in_sample)
    if not video or not audio:
        raise ExportError("Timeline needs both video and audio segments")
    chains: list[str] = []
    for index, clip in enumerate(video):
        chains.append(_video_chain(clip, media, index))
    for index, clip in enumerate(audio):
        chains.append(_audio_chain(clip, media, index))
    video_inputs = "".join(f"[v{index}]" for index in range(len(video)))
    audio_inputs = "".join(f"[a{index}]" for index in range(len(audio)))
    chains.append(f"{video_inputs}concat=n={len(video)}:v=1:a=0[vout]")
    chains.append(f"{audio_inputs}concat=n={len(audio)}:v=0:a=1[aout]")
    return ";".join(chains), "[vout]", "[aout]"


def export_mp4(
    state: ProjectState,
    output_path: Path,
    *,
    adapter: Any | None = None,
    crf: int = 18,
    preset: str = "medium",
) -> Path:
    """Render the validated main timeline to an H.264/AAC MP4."""

    media = state.media_info
    if media is None:
        raise ExportError("Project has no media")
    graph, video_label, audio_label = build_filter_graph(state)
    destination = Path(output_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    renderer = adapter or FFmpegAdapter()
    renderer.render(
        [
            "-i",
            str(Path(media.source_path).expanduser()),
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
    )
    if not destination.is_file():
        raise ExportError(f"FFmpeg did not write {destination.name}")
    return destination
