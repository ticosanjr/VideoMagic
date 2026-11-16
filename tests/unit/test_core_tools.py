"""Consolidated 12-tool core profile."""

from __future__ import annotations

from pathlib import Path

from videoflow.application.projects import init_project, save_project_state
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    Sentence,
    VideoSegment,
)
from videoflow.engine.batch import BatchManager
from videoflow.mcp_server.context import ToolContext
from videoflow.mcp_server.core_tools import register_core_tools


class Telemetry:
    def logs(self, **kwargs):
        return [{"module": "render", "message": "$ ffmpeg -i x"}]

    def stages(self):
        return []


class Job:
    def __init__(self, output: Path, project_id: str):
        self.job_id = "job-1"
        self.project_id = project_id
        self.output = output
        self.source = output / "source.mp4"
        self.status = "succeeded"
        self.stage = "done"
        self.progress = 100
        self.message = "done"
        self.result = {"artifacts": {}}
        self.error = None
        self.options = {"mode": "recipe"}
        self.created_at = "2026-01-01T00:00:00"
        self.telemetry = Telemetry()

    def to_dict(self, summary=False):
        return {"job_id": "job-1", "project_id": self.project_id, "status": self.status}


class Manager:
    def __init__(self, job):
        self.job = job

    def get(self, job_id):
        return self.job

    def list(self):
        return [self.job]

    def start(self, *args, **kwargs):
        return self.job

    def cancel(self, job_id):
        return self.job

    def update_result(self, job_id, result):
        self.job.result = result


def setup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    record, _ = init_project(output=tmp_path / "out")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )
    state = ProjectState(
        sources={"src1": media},
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_id="src1",
                source_in_frame=0,
                source_out_frame=30,
                timeline_in_frame=0,
                timeline_out_frame=30,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_id="src1",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            )
        ],
        transcript=[Sentence(id=0, start_sample=0, end_sample=1000, text="hello")],
    )
    save_project_state(record, state, bump_revision=False)
    (tmp_path / "out" / "exports").mkdir(parents=True)
    (tmp_path / "out" / "exports" / "note.txt").write_text("ok", encoding="utf-8")
    job = Job(tmp_path / "out", record.project_id)
    tools = {}

    def register(func):
        tools[func.__name__] = func
        return func

    register_core_tools(
        register,
        ToolContext(manager=Manager(job), batch_manager=BatchManager(Manager(job))),  # type: ignore[arg-type]
    )
    return tools, record, job


def test_core_project_catalog_exec_job(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = setup(tmp_path, monkeypatch)
    assert tools["vf_project"](action="status", project_id=record.project_id)["ok"] is True
    assert tools["vf_capabilities"]()["ok"] is True
    catalog = tools["vf_catalog_search"](query="session")
    assert any(step["type"] == "session.ingest" for step in catalog["steps"])
    assert catalog["recipes"] is not None

    executed = tools["vf_exec"](
        action="step",
        project_id=record.project_id,
        step_id="session.ingest",
        params={"sources": [str(tmp_path / "source.mp4")]},
    )
    assert executed["ok"] is True
    assert tools["vf_job"](action="get", project_id=record.project_id, job_id="job-1")["ok"] is True
    assert tools["vf_job"](action="logs", project_id=record.project_id, job_id="job-1")["commands"]


def test_core_timeline_artifact_render_exports(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = setup(tmp_path, monkeypatch)
    timeline = tools["vf_timeline"](action="get", project_id=record.project_id)
    assert timeline["video"][0]["source_id"] == "src1"
    edited = tools["vf_timeline"](
        action="edit",
        project_id=record.project_id,
        clip_id="v1",
        edit_action="trim",
        start_sec=0.0,
        end_sec=0.5,
    )
    assert edited["ok"] is True
    artifacts = tools["vf_artifact"](action="list", project_id=record.project_id)
    assert artifacts["artifacts"]
    artifact = tools["vf_artifact"](
        action="get", project_id=record.project_id, artifact="exports/note.txt"
    )
    assert artifact[0]["text"] == "ok"
    assert tools["vf_render"](action="start", project_id=record.project_id)["ok"] is True
    assert (
        tools["vf_render"](action="cancel", project_id=record.project_id, job_id="job-1")["ok"]
        is True
    )
    assert tools["vf_exports"](action="validate", project_id=record.project_id)["ok"] in {
        True,
        False,
    }
    assert tools["vf_qa"](action="artifacts", project_id=record.project_id)[0]["ok"] is True


def test_core_ingest_interaction_and_errors(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = setup(tmp_path, monkeypatch)
    assert tools["vf_ingest"](action="multicam", project_id=record.project_id)["ok"] is False
    assert tools["vf_project"](action="status", project_id="missing")["ok"] is False
    assert tools["vf_interaction"](action="list", project_id=record.project_id)["ok"] is True
    assert tools["vf_qa"](action="inspect", project_id=record.project_id)["ok"] is True


def test_core_catalog_and_project_errors(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = setup(tmp_path, monkeypatch)
    assert tools["vf_project"](action="status")["code"] == "project_required"
    assert tools["vf_catalog_search"](query="nomatch", kind="steps")["steps"] == []
    recipes = tools["vf_catalog_search"](kind="recipes", limit=1)["recipes"]
    assert len(recipes) == 1
    assert tools["vf_catalog_search"](kind="steps", limit=1)["steps"]
    assert tools["vf_exec"](action="step", project_id=record.project_id)["ok"] is False
    assert tools["vf_exec"](action="recipe", project_id="missing")["ok"] is False
    assert tools["vf_artifact"](action="list", project_id="missing")["ok"] is False


def test_core_job_wait_and_render_status(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = setup(tmp_path, monkeypatch)
    waited = tools["vf_job"](action="wait", project_id=record.project_id, job_id="job-1")
    assert waited["ok"] is True
    assert (
        tools["vf_render"](action="status", project_id=record.project_id, job_id="job-1")["ok"]
        is True
    )
    assert (
        tools["vf_exports"](action="roundtrip", project_id=record.project_id, direction="push")[
            "ok"
        ]
        is True
    )
    assert tools["vf_qa"](action="inspect", project_id="missing")["ok"] is False
    job.status = "running"
    assert (
        tools["vf_job"](action="wait", project_id=record.project_id, job_id="job-1", timeout_sec=1)[
            "code"
        ]
        == "timeout"
    )


def test_core_artifact_workspace_asset(tmp_path: Path, monkeypatch) -> None:
    from PIL import Image
    from vf_contracts.assets import write_asset
    from vf_contracts.workspace import ensure_project

    tools, record, job = setup(tmp_path, monkeypatch)
    ensure_project(record.project_id, name="Core", output=record.output)
    preview = tmp_path / "preview.png"
    Image.new("RGB", (8, 8)).save(preview)
    written = write_asset(
        record.project_id,
        "images",
        preview,
        {"license": "ai_generated", "source": "test", "ext": ".png"},
    )
    listed = tools["vf_artifact"](action="list", project_id=record.project_id)
    assert any(item.get("asset_id") == written.asset_id for item in listed["artifacts"])
    got = tools["vf_artifact"](
        action="get", project_id=record.project_id, artifact=written.asset_id
    )
    assert got[0]["asset_id"] == written.asset_id
    assert len(got) == 2


def test_core_interaction_and_job_branches(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = setup(tmp_path, monkeypatch)
    assert tools["vf_interaction"](action="list", project_id=record.project_id)["ok"] is True
    assert (
        tools["vf_interaction"](
            action="get", project_id=record.project_id, interaction_id="missing"
        )["ok"]
        is False
    )
    assert tools["vf_job"](action="qa", project_id=record.project_id)["ok"] is True
    assert (
        tools["vf_ingest"](action="session", project_id=record.project_id, sources=[])["ok"]
        is False
    )
    job.status = "failed"
    assert (
        tools["vf_job"](action="wait", project_id=record.project_id, job_id="job-1")["ok"] is False
    )


def test_core_artifact_missing_and_recipe_filter(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = setup(tmp_path, monkeypatch)
    missing = tools["vf_artifact"](action="get", project_id=record.project_id, artifact="missing")
    assert missing[0]["ok"] is False
    assert tools["vf_catalog_search"](query="no-such-recipe", kind="recipes")["recipes"] == []
