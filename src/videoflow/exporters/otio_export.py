"""OpenTimelineIO for Kdenlive 25.04+ and other OTIO hosts."""

from __future__ import annotations

from pathlib import Path

import opentimelineio as otio

from videoflow.domain.state import ProjectState
from videoflow.exporters.common import require_timeline


def export_otio(state: ProjectState, output_path: Path) -> Path:
    """Write an OTIO timeline with separate video and audio tracks."""

    media, _, _ = require_timeline(state)
    timebase = media.timebase()
    rate = timebase.fps_num / timebase.fps_den
    reference = otio.schema.ExternalReference(
        target_url=Path(media.source_path).expanduser().resolve().as_uri()
    )

    timeline = otio.schema.Timeline(name="VideoFlow")
    timeline.metadata["videoflow"] = {
        "fps_num": media.fps_num,
        "fps_den": media.fps_den,
        "audio_sample_rate": media.audio_sample_rate,
    }

    video_track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
    audio_track = otio.schema.Track(name="A1", kind=otio.schema.TrackKind.Audio)

    for clip in state.video_segments:
        video_clip = otio.schema.Clip(
            name=clip.clip_id,
            media_reference=reference,
            source_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(clip.source_in_frame, rate),
                duration=otio.opentime.RationalTime(
                    clip.source_out_frame - clip.source_in_frame, rate
                ),
            ),
        )
        video_clip.metadata["videoflow"] = {
            "clip_id": clip.clip_id,
            "transform": clip.transform.model_dump(mode="json"),
        }
        video_track.append(video_clip)

    for clip in state.audio_segments:
        audio_clip = otio.schema.Clip(
            name=clip.clip_id,
            media_reference=reference,
            source_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(
                    clip.source_in_sample, media.audio_sample_rate
                ),
                duration=otio.opentime.RationalTime(
                    clip.source_out_sample - clip.source_in_sample,
                    media.audio_sample_rate,
                ),
            ),
        )
        audio_clip.metadata["videoflow"] = {
            "clip_id": clip.clip_id,
            "fade_in_samples": clip.fade_in_samples,
            "fade_out_samples": clip.fade_out_samples,
        }
        audio_track.append(audio_clip)

    timeline.tracks.append(video_track)
    timeline.tracks.append(audio_track)

    target = Path(output_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    otio.adapters.write_to_file(timeline, str(target))
    return target
