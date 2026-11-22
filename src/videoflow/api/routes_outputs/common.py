"""Shared helpers for output routes."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405
from .deps import *


def _timeline_state_path(job: Job) -> Path:
    return Path(
        str((job.result or {}).get("state_path") or job.output / "project_state.json")
    )


def fail(exc: VideoFlowError) -> None:
    raise HTTPException(status_code=status_for(exc.code), detail=exc.to_dict()) from exc


def _frame_target(
    job: Any, revision: int, time_sec: float, height: int
) -> Path:
    stamp = int(max(0.0, min(time_sec, 24 * 3600)) * 10)
    height = max(64, min(2160, int(height)))
    return (
        job.output
        / "preview"
        / "frames"
        / str(revision)
        / f"{stamp:08d}-{height}.jpg"
    )


def _frame_source(
    state: ProjectState, moment: float, preview: Path | None
) -> tuple[Path, float]:
    """Map a timeline moment to the matching picture."""

    if preview is not None:
        return preview, moment
    media = state.media_info
    if media is None:
        raise StateNotReadyError("The project has no media info.")
    source = Path(media.source_path).expanduser()
    if not source.is_file():
        raise StateNotReadyError("The source media is not available.")
    fps = media.fps_num / media.fps_den
    frame = int(max(0.0, moment) * fps)
    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    if not video:
        return source, moment
    chosen = video[-1]
    for clip in video:
        if clip.timeline_in_frame <= frame < clip.timeline_out_frame:
            chosen = clip
            break
    offset = max(0, frame - chosen.timeline_in_frame)
    source_frame = min(
        chosen.source_out_frame - 1,
        chosen.source_in_frame + offset,
    )
    return source, source_frame / fps
