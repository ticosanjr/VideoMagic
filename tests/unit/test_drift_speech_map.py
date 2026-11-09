from __future__ import annotations

import json
from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, Sentence
from videoflow.steps.alignment import DriftCorrectionStep, DriftParams
from videoflow.steps.base import StepIO


def test_drift_writes_frame_accurate_speech_map(tmp_path: Path) -> None:
    output = tmp_path / "out"
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
        media=MediaInfo(
            source_path=str(tmp_path / "source.mp4"),
            duration_frames=250,
            fps_num=25,
            fps_den=1,
            width=640,
            height=360,
            audio_sample_rate=48000,
        ),
        transcript=[
            Sentence(id=0, start_sample=0, end_sample=48000, text="Hello"),
        ],
    )
    DriftCorrectionStep().run(context, DriftParams(offset_ms=200), StepIO())
    payload = json.loads(
        (output / "alignment" / "speech-map.json").read_text(encoding="utf-8")
    )
    assert payload["fps"] == 25.0
    segment = payload["segments"][0]
    assert segment["start_frame"] == 0
    assert segment["end_frame"] == 20
    assert segment["end_sec"] == 0.8
    assert context.metadata["drift_correction"]["offset_frames"] == 5
