"""Speaker-turn labeling for speaker-colored captions.

The default is a pause-based heuristic. ``pyannote`` is available as an
optional model-based method when the extra dependency and model are installed.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.diarization import PyannoteDiarizer, assign_speakers
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import CapabilityUnavailableError, IngestError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class DiarizeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["heuristic", "pyannote", "none"] = "heuristic"
    pause_ms: int = Field(default=400, ge=50, le=5000)
    max_speakers: int = Field(default=4, ge=1, le=12)
    model_path: str = "pyannote/speaker-diarization-3.1"
    device: str | None = None
    hf_token_env: str = "HF_TOKEN"
    fallback_to_heuristic: bool = True


def _heuristic(sentences, *, pause: int, max_speakers: int):
    speaker = 0
    previous_end: int | None = None
    updated = []
    for sentence in sorted(sentences, key=lambda item: item.start_sample):
        if previous_end is not None and sentence.start_sample - previous_end >= pause:
            speaker = (speaker + 1) % max_speakers
        updated.append(sentence.model_copy(update={"speaker": speaker}))
        previous_end = sentence.end_sample
    return updated


@register_step
class DiarizeStep(BaseStep):
    type = "audio.diarize"
    title = "Speaker turns"
    description = (
        "Assign speaker ids by pause heuristic or by an optional pyannote model."
    )
    requires = ("transcribe",)
    produces = ("speaker_turns",)
    params_model = DiarizeParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = DiarizeParams.model_validate(params)
        if not context.transcript:
            raise IngestError("Speaker turns require a transcript.")
        if options.method == "none":
            io.report(100, "Speaker turns disabled")
            return
        media = context.media
        sample_rate = media.audio_sample_rate if media is not None else 48000
        pause = max(1, round(options.pause_ms * sample_rate / 1000))
        updated = None
        if options.method == "pyannote":
            io.report(15, "Loading diarization model")
            if context.pcm_path is None or not Path(context.pcm_path).is_file():
                raise IngestError("Model-based diarization needs the extracted PCM audio.")
            token = os.environ.get(options.hf_token_env) or None
            model_path = options.model_path
            if model_path in ("", "pyannote/speaker-diarization-3.1"):
                from videoflow.application.models import installed_path

                local = installed_path("pyannote-diarization-3.1")
                if local is not None:
                    model_path = str(local)
            try:
                turns = PyannoteDiarizer(
                    model_path=model_path,
                    device=options.device,
                    hf_token=token,
                ).diarize(Path(context.pcm_path), sample_rate=sample_rate)
            except CapabilityUnavailableError as exc:
                if not options.fallback_to_heuristic:
                    raise
                context.warnings.append(f"{exc} Falling back to pause heuristic.")
                turns = []
            if turns:
                updated = assign_speakers(context.transcript, turns)
                context.metadata["diarization_method"] = "pyannote"
                context.metadata["diarization_turns"] = len(turns)
        if updated is None:
            updated = _heuristic(
                context.transcript,
                pause=pause,
                max_speakers=options.max_speakers,
            )
            context.metadata["diarization_method"] = "heuristic"
        context.transcript = updated
        context.metadata["speaker_count"] = len({item.speaker for item in updated})
        context.hashes["diarize"] = digest_payload(
            [(item.id, item.speaker) for item in updated]
        )
        io.emit(
            "info",
            f"{context.metadata['speaker_count']} speaker turns",
            module="diarize",
        )
        io.report(100, "Speaker turns ready")
