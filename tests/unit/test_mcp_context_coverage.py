"""ToolContext project/job helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.domain.errors import StateNotReadyError
from videoflow.domain.state import MediaInfo, ProjectState, Sentence
from videoflow.mcp_server.context import ToolContext


class Manager:
    def __init__(self, job):
        self.job = job

    def get(self, job_id):
        if self.job is None or str(job_id) != self.job.job_id:
            raise StateNotReadyError("missing")
        return self.job


def _state(path: Path, tmp_path: Path) -> Path:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    state = ProjectState(
        media_info=MediaInfo(
            source_path=str(source),
            duration_frames=30,
            fps_num=30,
            fps_den=1,
            width=320,
            height=240,
            audio_sample_rate=44100,
        ),
        transcript=[Sentence(id=0, start_sample=0, end_sample=1000, text="hello")],
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(), encoding="utf-8")
    return state.source_media()  # type: ignore[return-value]


def test_context_project_and_transcript(tmp_path: Path) -> None:
    output = tmp_path / "out"
    media = _state(output / "project_state.json", tmp_path)
    ctx = ToolContext(manager=Manager(None), batch_manager=None)  # type: ignore[arg-type]
    assert ctx.project_state() is None
    ctx.last["output"] = output
    state = ctx.project_state()
    assert state is not None
    assert ctx.transcript_for()[0].text == "hello"
    assert ctx.sample_rate(state) == 44100
    ctx.last["transcript"] = [Sentence(id=1, start_sample=0, end_sample=10, text="cached")]
    assert ctx.transcript_for()[0].text == "cached"
    assert ctx.sample_rate(None) == 48000
    ctx.last["media"] = media
    assert ctx.sample_rate(None) == 44100
    ctx.last["transcript"] = []
    ctx.last["output"] = output / "missing"
    assert ctx.project_state() is None
    assert ctx.transcript_for() is None


def test_context_job_state_and_errors(tmp_path: Path) -> None:
    output = tmp_path / "out"
    media = _state(output / "project_state.json", tmp_path)
    job = SimpleNamespace(
        job_id="job-1",
        output=output,
        result={"state_path": str(output / "project_state.json")},
    )
    ctx = ToolContext(manager=Manager(job), batch_manager=None)  # type: ignore[arg-type]
    with pytest.raises(StateNotReadyError):
        ctx.timeline_job()
    ctx.last["job_id"] = "job-1"
    assert ctx.timeline_job().job_id == "job-1"
    assert ctx.state_for_job(job) is not None
    job.result = {"state_path": str(output / "missing.json")}
    assert ctx.state_for_job(job) is None
    (output / "project_state.json").write_text("{", encoding="utf-8")
    assert ctx.state_for_job(job) is None
    assert media.audio_sample_rate == 44100
