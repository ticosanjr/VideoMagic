"""CMX 3600 EDL export for legacy NLE interchange."""

from __future__ import annotations

from pathlib import Path

from videoflow.domain.state import ProjectState
from videoflow.exporters.common import (
    require_timeline,
    timeline_duration_frames,
    write_text,
)


def _timecode(frames: int, fps: int) -> str:
    fps = max(1, fps)
    total_seconds, frame = divmod(max(0, frames), fps)
    minutes, second = divmod(total_seconds, 60)
    hour, minute = divmod(minutes, 60)
    return f"{hour:02d}:{minute:02d}:{second:02d}:{frame:02d}"


def export_edl(
    state: ProjectState,
    output_path: Path,
    *,
    title: str = "VideoFlow",
) -> Path:
    """Write a video-only CMX 3600 EDL from the canonical timeline."""

    media, _video_by_id, _audio_by_id = require_timeline(state)
    fps = max(1, round(media.fps_num / media.fps_den))
    source_name = Path(media.source_path).name
    lines = [
        f"TITLE: {title}",
        "FCM: NON-DROP FRAME",
        "",
    ]
    clips = sorted(state.video_segments, key=lambda clip: clip.timeline_in_frame)
    for index, clip in enumerate(clips, start=1):
        lines.append(
            f"{index:03d}  AX       V     C        "
            f"{_timecode(clip.source_in_frame, fps)} "
            f"{_timecode(clip.source_out_frame, fps)} "
            f"{_timecode(clip.timeline_in_frame, fps)} "
            f"{_timecode(clip.timeline_out_frame, fps)}"
        )
        lines.append(f"* FROM CLIP NAME: {source_name}")
        lines.append("")
    lines.append(f"* TOTAL DURATION: {_timecode(timeline_duration_frames(state), fps)}")
    return write_text(Path(output_path), "\n".join(lines).rstrip() + "\n")
