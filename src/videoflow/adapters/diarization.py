"""Optional model-based speaker diarization.

The ``pyannote.audio`` dependency is intentionally optional. When it is not
installed, the caller can keep the heuristic pause-based labels or surface a
typed capability error.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from videoflow.domain.errors import CapabilityUnavailableError
from videoflow.domain.state import Sentence


@dataclass(frozen=True, slots=True)
class SpeakerTurn:
    start_sample: int
    end_sample: int
    speaker: str


def assign_speakers(
    sentences: Sequence[Sentence],
    turns: Sequence[SpeakerTurn],
) -> list[Sentence]:
    """Assign each sentence the model speaker with the largest overlap."""

    labels = sorted({turn.speaker for turn in turns})
    ids = {label: index for index, label in enumerate(labels)}
    updated: list[Sentence] = []
    for sentence in sentences:
        best_label = None
        best_overlap = 0
        for turn in turns:
            overlap = max(
                0,
                min(sentence.end_sample, turn.end_sample)
                - max(sentence.start_sample, turn.start_sample),
            )
            if overlap > best_overlap:
                best_overlap = overlap
                best_label = turn.speaker
        speaker = ids.get(best_label, 0) if best_label is not None else 0
        updated.append(sentence.model_copy(update={"speaker": speaker}))
    return updated


class PyannoteDiarizer:
    """Thin lazy wrapper around ``pyannote.audio``."""

    def __init__(
        self,
        *,
        model_path: str = "pyannote/speaker-diarization-3.1",
        device: str | None = None,
        hf_token: str | None = None,
    ) -> None:
        self.model_path = model_path
        self.device = device
        self.hf_token = hf_token

    def diarize(self, audio_path: Path, *, sample_rate: int) -> list[SpeakerTurn]:
        try:
            import torch
            from pyannote.audio import Pipeline
        except ImportError as exc:
            raise CapabilityUnavailableError(
                "diarization",
                "Model-based diarization requires the optional pyannote.audio "
                "dependency. Install the diarization extra or keep the heuristic method.",
            ) from exc
        try:
            pipeline = Pipeline.from_pretrained(
                self.model_path,
                use_auth_token=self.hf_token,
            )
        except Exception as exc:
            raise CapabilityUnavailableError(
                "diarization",
                f"Could not load diarization model {self.model_path}: {exc}",
            ) from exc
        if self.device:
            pipeline.to(torch.device(self.device))
        diarization = pipeline(str(Path(audio_path).expanduser()))
        turns: list[SpeakerTurn] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            turns.append(
                SpeakerTurn(
                    start_sample=round(turn.start * sample_rate),
                    end_sample=round(turn.end * sample_rate),
                    speaker=str(speaker),
                )
            )
        return turns
