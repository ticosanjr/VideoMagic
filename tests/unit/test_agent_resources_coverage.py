"""Project resources and prompts for the agent profile."""

from __future__ import annotations

import json
from pathlib import Path

from videoflow.application.projects import init_project, save_project_state
from videoflow.domain.state import MediaInfo, ProjectState, Sentence
from videoflow.mcp_server.agent_resources import register_agent_resources
from videoflow.mcp_server.context import ToolContext


class FakeJob:
    job_id = "job-1"
    output: Path
    project_id: str
    status = "succeeded"

    def __init__(self, output: Path, project_id: str):
        self.output = output
        self.project_id = project_id

    def to_dict(self, summary=False):
        return {"job_id": self.job_id, "project_id": self.project_id, "status": self.status}


class FakeManager:
    def __init__(self, job):
        self.job = job

    def list(self):
        return [self.job]

    def get(self, job_id):
        return self.job


class FakeMCP:
    def __init__(self):
        self.resources = {}
        self.prompts = {}

    def resource(self, uri):
        def decorate(func):
            self.resources[uri] = func
            return func

        return decorate

    def prompt(self, name, description=""):
        def decorate(func):
            self.prompts[name] = func
            return func

        return decorate


def _setup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    record, _ = init_project(output=tmp_path / "out")
    state = ProjectState(
        project_id=record.project_id,  # type: ignore[arg-type]
        sources={
            "src1": MediaInfo(
                source_path=str(source),
                duration_frames=30,
                fps_num=30,
                fps_den=1,
                width=320,
                height=240,
                audio_sample_rate=48000,
            )
        },
        transcript=[Sentence(id=0, start_sample=0, end_sample=1000, text="hello")],
    )
    save_project_state(record, state, bump_revision=False)
    (tmp_path / "out" / "exports").mkdir()
    (tmp_path / "out" / "exports" / "x.txt").write_text("x", encoding="utf-8")
    (tmp_path / "out" / "job.log").write_text("log line\n", encoding="utf-8")
    channels = tmp_path / "home" / "channels"
    channels.mkdir(parents=True)
    (channels / "demo.json").write_text(
        json.dumps(
            {
                "channel_id": "demo",
                "hard_constraints": {"palette": "light"},
                "learned_rules": [{"id": "r1", "text": "cut at 4s"}],
                "channel_kit": {"fonts": ["Inter"]},
            }
        ),
        encoding="utf-8",
    )
    job = FakeJob(tmp_path / "out", record.project_id)
    mcp = FakeMCP()
    register_agent_resources(
        mcp,
        ToolContext(manager=FakeManager(job), batch_manager=None),  # type: ignore[arg-type]
    )
    return mcp, record


def test_project_resources_and_prompts(tmp_path: Path, monkeypatch) -> None:
    mcp, record = _setup(tmp_path, monkeypatch)
    assert json.loads(mcp.resources["vf://projects"]())["projects"]
    state = json.loads(mcp.resources["vf://projects/{project_id}/state"](record.project_id))
    assert state["transcript"][0]["text"] == "hello"
    timeline = json.loads(mcp.resources["vf://projects/{project_id}/timeline"](record.project_id))
    assert timeline["primary_source_id"] == "src1"
    srt = mcp.resources["vf://projects/{project_id}/transcript"](record.project_id)
    assert "hello" in srt
    jobs = json.loads(mcp.resources["vf://projects/{project_id}/jobs"](record.project_id))
    assert jobs["jobs"][0]["job_id"] == "job-1"
    artifacts = json.loads(mcp.resources["vf://projects/{project_id}/artifacts"](record.project_id))
    assert artifacts["artifacts"]
    logs = mcp.resources["vf://projects/{project_id}/jobs/{job_id}/logs"](
        record.project_id, "job-1"
    )
    assert "log line" in logs
    assert "***" not in logs

    rulebook = json.loads(mcp.resources["vf://presets/{channel_id}/rulebook"]("demo"))
    assert rulebook["hard_constraints"]["palette"] == "light"
    kit = json.loads(mcp.resources["vf://presets/{channel_id}/kit"]("demo"))
    assert kit["fonts"] == ["Inter"]
    step = json.loads(mcp.resources["vf://docs/steps/{step_type}"]("session.ingest"))
    assert "sources" in step["schema"]["properties"]
    recipe = json.loads(mcp.resources["vf://docs/recipes/{recipe_id}"]("youtube_talking_head"))
    assert recipe["id"] == "youtube_talking_head"

    assert "vf_exec" in mcp.prompts["videoflow_produce"]("p", "youtube_talking_head")
    assert "vf_qa" in mcp.prompts["videoflow_review"]("p", "j")
    assert "bundle" in mcp.prompts["videoflow_deliver"]("p").lower()


def test_resource_error_paths(tmp_path: Path, monkeypatch) -> None:
    mcp, _record = _setup(tmp_path, monkeypatch)
    missing = "00000000-0000-0000-0000-000000000000"
    assert json.loads(mcp.resources["vf://projects/{project_id}/state"](missing))["ok"] is False
    assert json.loads(mcp.resources["vf://projects/{project_id}/jobs"](missing))["ok"] is False
    assert json.loads(mcp.resources["vf://projects/{project_id}/artifacts"](missing))["ok"] is False
    assert (
        json.loads(
            mcp.resources["vf://projects/{project_id}/jobs/{job_id}/logs"](missing, "job-1")
        )["ok"]
        is False
    )
    assert json.loads(mcp.resources["vf://docs/steps/{step_type}"]("missing.step"))["ok"] is False
    assert json.loads(mcp.resources["vf://docs/recipes/{recipe_id}"]("missing"))["ok"] is False


def test_layout_preview_artifact_branch(tmp_path: Path) -> None:
    from videoflow.core.context import PipelineContext
    from videoflow.steps.base import StepIO
    from videoflow.steps.layout_cutout import CutoutLayoutStep, CutoutParams

    output = tmp_path / "out"
    (output / "work").mkdir(parents=True)
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )
    preview = tmp_path / "preview.mp4"
    preview.write_bytes(b"mp4")
    step = CutoutLayoutStep()
    step._render_preview = lambda context, options: preview  # type: ignore[method-assign]
    step.run(context, CutoutParams(render_preview=True), StepIO())
    assert context.artifacts["layout_preview"] == str(preview)
