"""Engine contracts. They are expected to fail until each pass is implemented."""

from pathlib import Path

import pytest

from videoflow.adapters import FasterWhisperAdapter, FFmpegAdapter
from videoflow.application.runner import PipelineRunner
from videoflow.domain.errors import IngestError
from videoflow.domain.planning import RunPlan
from videoflow.domain.state import ProjectState
from videoflow.modules import modules


def test_ingest_reports_a_missing_source(tmp_path: Path) -> None:
    with pytest.raises(IngestError):
        FFmpegAdapter().probe(tmp_path / "missing.mp4")


@pytest.mark.parametrize("module", modules(), ids=lambda item: item.id)
@pytest.mark.xfail(reason="Module engines land pass by pass", strict=True)
def test_each_module_executes(module: object) -> None:
    assert module.execute(object()) is not None  # type: ignore[attr-defined]


@pytest.mark.xfail(reason="Faster-Whisper engine is not in this pass", strict=True)
def test_transcribe(tmp_path: Path) -> None:
    FasterWhisperAdapter().transcribe(tmp_path / "source.wav")


@pytest.mark.xfail(reason="Runner execution is not in the scaffold", strict=True)
def test_runner_executes() -> None:
    PipelineRunner().execute(ProjectState(), RunPlan(modules=("ingest",), skipped=()))
