"""Apply retake discards to an existing multi-source session timeline."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.retake_spans import cull_intervals
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import StateNotReadyError
from videoflow.domain.state import AudioSegment, VideoSegment
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class SessionCullParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discard_sentence_ids: list[int] = Field(default_factory=list)


def _keep_ranges(start: int, end: int, cuts: list[tuple[int, int]]) -> list[tuple[int, int]]:
    ranges = [(start, end)]
    for cut_start, cut_end in cuts:
        next_ranges: list[tuple[int, int]] = []
        for left, right in ranges:
            if cut_end <= left or cut_start >= right:
                next_ranges.append((left, right))
                continue
            if cut_start > left:
                next_ranges.append((left, cut_start))
            if cut_end < right:
                next_ranges.append((cut_end, right))
        ranges = next_ranges
    return [(left, right) for left, right in ranges if right > left]


@register_step
class SessionCullStep(BaseStep):
    type = "session.cull"
    title = "Session cull"
    description = "Apply retake discards to a multi-source session timeline without rebuilding it."
    produces = ("timeline", "session_cull_report")
    params_model = SessionCullParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = SessionCullParams.model_validate(params)
        if context.state is None:
            raise StateNotReadyError("Session cull requires an existing timeline")
        if context.media is None:
            raise StateNotReadyError("Session cull requires media info")
        state = context.state
        rate = context.media.audio_sample_rate
        fps = context.media.fps_num / context.media.fps_den
        discard = options.discard_sentence_ids or list(context.discard_sentence_ids)
        cut_samples = cull_intervals(context.transcript, discard)
        cut_frames = [
            (round(start / rate * fps), round(end / rate * fps)) for start, end in cut_samples
        ]
        video: list[VideoSegment] = []
        audio: list[AudioSegment] = []
        video_cursor = 0
        audio_cursor = 0
        for original in sorted(state.video_segments, key=lambda item: item.timeline_in_frame):
            for start, end in _keep_ranges(
                original.timeline_in_frame, original.timeline_out_frame, cut_frames
            ):
                duration = end - start
                if duration <= 0:
                    continue
                source_shift = start - original.timeline_in_frame
                clip = original.model_copy(
                    update={
                        "clip_id": f"{original.clip_id}-{len(video) + 1:02d}",
                        "source_in_frame": original.source_in_frame + source_shift,
                        "source_out_frame": original.source_in_frame + source_shift + duration,
                        "timeline_in_frame": video_cursor,
                        "timeline_out_frame": video_cursor + duration,
                    }
                )
                video.append(clip)
                video_cursor += duration
        for original in sorted(state.audio_segments, key=lambda item: item.timeline_in_sample):
            for start, end in _keep_ranges(
                original.timeline_in_sample, original.timeline_out_sample, cut_samples
            ):
                duration = end - start
                if duration <= 0:
                    continue
                source_shift = start - original.timeline_in_sample
                clip = original.model_copy(
                    update={
                        "clip_id": f"{original.clip_id}-{len(audio) + 1:02d}",
                        "source_in_sample": original.source_in_sample + source_shift,
                        "source_out_sample": original.source_in_sample + source_shift + duration,
                        "timeline_in_sample": audio_cursor,
                        "timeline_out_sample": audio_cursor + duration,
                    }
                )
                audio.append(clip)
                audio_cursor += duration
        if not video or not audio:
            raise StateNotReadyError("Session cull removed every clip")
        updated = state.model_copy(
            update={
                "video_segments": video,
                "audio_segments": audio,
                "retake_culls": list(discard),
            }
        )
        context.state = updated
        report = {
            "discarded_sentences": len(discard),
            "cut_spans": [list(item) for item in cut_samples],
            "video_segments": len(video),
            "audio_segments": len(audio),
        }
        context.metadata["session_cull_report"] = report
        context.hashes["session.cull"] = digest_payload(report)
        io.report(100, f"Session cull: {len(video)} clip(s) remain")
