"""Direct coverage for the 22 agent tools and project resources."""

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
from videoflow.mcp_server.agent_tools import register_agent_tools
from videoflow.mcp_server.context import ToolContext


class FakeTelemetry:
    def logs(self, *, limit=500):
        return [
            {"module": "render", "level": "info", "message": "$ ffmpeg -i x"},
            {"module": "render", "level": "error", "message": "boom"},
        ][-limit:]

    def stages(self):
        return [{"id": "render", "status": "failed", "duration_ms": 10}]


class FakeJob:
    def __init__(self, output: Path, project_id: str, *, status: str = "succeeded"):
        self.job_id = "job-1"
        self.status = status
        self.stage = "render"
        self.progress = 100 if status == "succeeded" else 10
        self.message = "done"
        self.output = output
        self.source = output / "source.mp4"
        self.project_id = project_id
        self.result = {"artifacts": {}}
        self.options = {"mode": "recipe"}
        self.error = None
        self.created_at = "2026-01-01T00:00:00"
        self.telemetry = FakeTelemetry()

    def to_dict(self, summary=False):
        return {
            "job_id": self.job_id,
            "project_id": self.project_id,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
        }


class FakeManager:
    def __init__(self, job: FakeJob | None = None):
        self.job = job
        self.started: list[FakeJob] = []

    def get(self, job_id):
        if self.job is None or str(job_id) != self.job.job_id:
            from videoflow.domain.errors import JobNotFoundError

            raise JobNotFoundError(str(job_id))
        return self.job

    def list(self):
        return [self.job] if self.job is not None else []

    def start(self, source, output, options=None, **kwargs):
        assert self.job is not None
        self.started.append(self.job)
        return self.job

    def update_result(self, job_id, result):
        assert self.job is not None
        self.job.result = result
        return self.job


def _media(source: Path) -> MediaInfo:
    return MediaInfo(
        source_path=str(source),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )


def _project(tmp_path: Path, monkeypatch) -> tuple:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    record, _ = init_project(output=tmp_path / "out")
    state = ProjectState(
        project_id=record.project_id,  # type: ignore[arg-type]
        sources={"src1": _media(source)},
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
    (tmp_path / "out" / "exports").mkdir(exist_ok=True)
    (tmp_path / "out" / "exports" / "note.txt").write_text("ok", encoding="utf-8")
    job = FakeJob(tmp_path / "out", record.project_id)
    tools: dict = {}

    def register(func):
        tools[func.__name__] = func
        return func

    manager = FakeManager(job)
    register_agent_tools(
        register,
        ToolContext(manager=manager),  # type: ignore[arg-type]
    )
    return tools, record, job


def test_agent_tool_success_paths(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = _project(tmp_path, monkeypatch)
    assert tools["vf_project_init"](project_id=record.project_id)["ok"] is True
    assert tools["vf_project_status"](project_id=record.project_id)["ok"] is True
    assert tools["vf_capabilities"]()["ok"] is True
    assert tools["vf_get_job"](project_id=record.project_id, job_id="job-1")["ok"] is True
    logs = tools["vf_get_step_logs"](project_id=record.project_id, job_id="job-1", step_id="render")
    assert logs["commands"]
    assert tools["vf_get_qa_artifacts"](project_id=record.project_id)[0]["ok"] is True
    assert tools["vf_get_timeline"](project_id=record.project_id)["ok"] is True
    artifact = tools["vf_get_artifact"](project_id=record.project_id, artifact="exports/note.txt")
    assert artifact[0]["text"] == "ok"
    assert tools["vf_validate_exports"](project_id=record.project_id)["ok"] in {True, False}
    assert tools["vf_nle_roundtrip"](project_id=record.project_id, direction="push")["ok"] is True
    assert tools["vf_render_start"](project_id=record.project_id)["ok"] is True
    assert (
        tools["vf_edit_timeline"](
            project_id=record.project_id,
            clip_id="v1",
            action="trim",
            start_sec=0.0,
            end_sec=0.5,
        )["ok"]
        is True
    )


def test_agent_tool_error_paths(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = _project(tmp_path, monkeypatch)
    assert tools["vf_project_init"]()["code"] == "output_required"
    assert tools["vf_ingest_session"](record.project_id)["ok"] is False
    assert tools["vf_sync_multicam"](record.project_id)["ok"] is False
    assert tools["vf_edit_short"](record.project_id, index=9)["ok"] is False
    assert tools["vf_respond_interaction"](record.project_id, "missing")["ok"] is False
    assert tools["vf_get_artifact"](record.project_id, "missing")[0]["ok"] is False
    assert (
        tools["vf_edit_timeline"](record.project_id, "missing", "trim", expected_revision=999)["ok"]
        is False
    )


def test_agent_tool_project_adoption_and_missing_job(tmp_path: Path, monkeypatch) -> None:
    tools, record, _job = _project(tmp_path, monkeypatch)
    adopted = tools["vf_project_init"](project_id=record.project_id)
    assert adopted["ok"] is True
    assert adopted["summary"]["sources"]
    assert tools["vf_get_job"](record.project_id, "missing")["ok"] is False
    assert "report" in tools["vf_nle_roundtrip"](record.project_id, direction="pull", path="")


def test_agent_tool_session_and_edit_short(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = _project(tmp_path, monkeypatch)
    ingested = tools["vf_ingest_session"](record.project_id, sources=[str(tmp_path / "source.mp4")])
    assert ingested["ok"] is True

    job.result = {
        "shorts": [
            {
                "title": "One",
                "pieces": [[0, 1000]],
                "aspect_ratio": "9:16",
            }
        ]
    }

    def fake_edit_short(**kwargs):
        return {"shorts": [{"title": "Edited", "path": str(tmp_path / "edited.mp4")}]}

    monkeypatch.setattr("videoflow.application.short_editor.edit_short", fake_edit_short)
    edited = tools["vf_edit_short"](record.project_id, index=0, title="Edited")
    assert edited["ok"] is True
    assert edited["short"]["title"] == "Edited"


def test_agent_tool_sync_and_interaction(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = _project(tmp_path, monkeypatch)
    state = tools["vf_get_timeline"](record.project_id)
    monkeypatch.setattr(
        "videoflow.application.multicam.sync_multicam",
        lambda state, directory, **kwargs: {
            "state": state,
            "manifest": str(tmp_path / "multicam.json"),
            "offset_ms": 0.0,
            "confidence": 1.0,
            "drift_ms": 0.0,
            "applied": True,
        },
    )
    synced = tools["vf_sync_multicam"](
        record.project_id,
        primary_source_id="src1",
        secondary_source_id="src2",
        min_confidence=0.0,
    )
    assert synced["ok"] is True
    assert "offset_ms" in synced["report"]

    class FakeRequest:
        interaction_id = "i1"
        status = "pending"

    class FakeResponse:
        pass

    monkeypatch.setattr(
        "videoflow.mcp_server.agent_tools.respond",
        lambda *args, **kwargs: (FakeRequest(), FakeResponse()),
    )
    monkeypatch.setattr(
        "videoflow.mcp_server.agent_tools.public_payload",
        lambda *args, **kwargs: {"interaction_id": "i1"},
    )
    answered = tools["vf_respond_interaction"](
        record.project_id, "i1", action="approve", job_id="job-1"
    )
    assert answered["ok"] is True
    assert state["ok"] is True


def test_agent_tool_more_branches(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = _project(tmp_path, monkeypatch)

    def fake_probe(self, path):
        return _media(Path(path))

    monkeypatch.setattr("videoflow.adapters.ffmpeg.FFmpegAdapter.probe", fake_probe)
    source = tmp_path / "source.mp4"
    adopted = tools["vf_project_init"](project_id=record.project_id, sources=[str(source)])
    assert adopted["ok"] is True

    assert tools["vf_project_status"]("missing")["ok"] is False
    job.telemetry.logs = lambda **kwargs: []
    logs = tools["vf_get_step_logs"](record.project_id, "job-1")
    assert logs["ok"] is True

    pushed = tools["vf_nle_roundtrip"](record.project_id, direction="push")
    assert pushed["ok"] is True
    pulled = tools["vf_nle_roundtrip"](
        record.project_id,
        direction="pull",
        path=str(tmp_path / "out" / "exports" / "timeline.fcpxml"),
    )
    assert pulled["ok"] is True

    ingested = tools["vf_ingest_session"](record.project_id, raw_dir=str(tmp_path))
    assert ingested["ok"] is True, ingested
    assert (
        tools["vf_ingest_session"](record.project_id, raw_dir=str(tmp_path / "missing-dir"))["ok"]
        is False
    )

    empty = tmp_path / "empty"
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home2"))
    empty_record, _ = init_project(output=empty)
    assert tools["vf_get_timeline"](empty_record.project_id)["ok"] is True


def test_adopt_job_and_qa_images(tmp_path: Path, monkeypatch) -> None:
    from PIL import Image

    from videoflow.mcp_server.agent_tools import _adopt_job

    tools, record, job = _project(tmp_path, monkeypatch)
    output = Path(record.output)
    qa = output / "work" / "qa"
    qa.mkdir(parents=True)
    Image.new("RGB", (8, 8)).save(qa / "frame.jpg")
    (qa / "qa_report.json").write_text(
        '{"defects": [{"kind": "flash"}], "passed": false}', encoding="utf-8"
    )
    result = tools["vf_get_qa_artifacts"](record.project_id, include_images=True)
    assert any(getattr(item, "path", None) for item in result[1:])
    (output / "project_state.json").write_text(
        '{"schema_version": 1, "video_segments": [], "audio_segments": []}',
        encoding="utf-8",
    )
    _adopt_job(record, job)
    assert (output / "project_state.json").is_file()


def test_agent_tool_resolve_errors_and_adoption(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application.projects import init_project
    from videoflow.mcp_server.agent_tools import _adopt_job

    tools, record, job = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "videoflow.adapters.resolve.resolve_roundtrip",
        lambda context, **kwargs: {"ok": True, "markers": [], "clips": []},
    )
    resolved = tools["vf_nle_roundtrip"](record.project_id, direction="pull", nle="resolve")
    assert resolved["ok"] is True
    assert tools["vf_validate_exports"]("missing")["ok"] is False
    assert tools["vf_get_qa_artifacts"]("missing")[0]["ok"] is False

    (Path(record.output) / "job.log").write_text("fallback line\n", encoding="utf-8")
    job.telemetry.logs = lambda **kwargs: []
    logs = tools["vf_get_step_logs"](record.project_id, "job-1")
    assert logs["logs"][0]["line"] == "fallback line"

    assert tools["vf_edit_timeline"](record.project_id, "v1", "invalid")["ok"] is False

    (Path(record.output) / "state.json").unlink(missing_ok=True)
    (Path(record.output) / "project_state.json").write_text("{", encoding="utf-8")
    assert tools["vf_get_timeline"](record.project_id, "job-1")["ok"] is False
    assert tools["vf_render_start"](record.project_id)["ok"] is False
    _adopt_job(record, job)

    empty_record, _ = init_project(output=tmp_path / "empty-two")
    assert tools["vf_project_init"](project_id=empty_record.project_id)["ok"] is True


def test_agent_tool_remaining_branches(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    from videoflow.application.projects import init_project, load_project_state, save_project_state
    from videoflow.mcp_server.agent_tools import _adopt_job

    tools, record, job = _project(tmp_path, monkeypatch)
    assert tools["vf_project_status"]("missing")["ok"] is False
    assert tools["vf_get_job"](record.project_id, "missing")["ok"] is False
    assert tools["vf_get_step_logs"](record.project_id, "missing")["ok"] is False
    created = tools["vf_project_init"](project_id="missing")
    assert created["ok"] is True
    assert created["project"]["project_id"] == "missing"

    qa = Path(record.output) / "work" / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    (qa / "qa_report.json").write_text('{"defects": [{"kind": "flash"}]}', encoding="utf-8")
    assert tools["vf_get_job"](record.project_id, "job-1")["job"]["qa"]["passed"] is False

    foreign = SimpleNamespace(
        job_id="job-2",
        project_id="other",
        output=tmp_path / "other",
        created_at="2026-01-01",
    )
    original_output = job.output
    job.project_id = "other"
    job.output = tmp_path / "other"
    assert tools["vf_get_job"](record.project_id, "job-1")["ok"] is False
    job.project_id = record.project_id
    job.output = original_output

    empty_record, _ = init_project(output=tmp_path / "no-state")
    assert tools["vf_nle_roundtrip"](empty_record.project_id, direction="push")["ok"] is False
    (Path(empty_record.output) / "state.json").unlink(missing_ok=True)
    (Path(empty_record.output) / "project_state.json").write_text("{", encoding="utf-8")
    assert tools["vf_render_start"](empty_record.project_id)["ok"] is False

    monkeypatch.setattr(
        "videoflow.application.multicam.sync_multicam",
        lambda state, directory, **kwargs: {
            "state": state,
            "manifest": str(tmp_path / "m.json"),
            "offset_ms": 1.0,
            "confidence": 1.0,
            "drift_ms": 0.0,
            "applied": True,
        },
    )
    current = load_project_state(record)
    current.sources["src2"] = current.sources["src1"]
    save_project_state(record, current, bump_revision=False)
    assert (
        tools["vf_sync_multicam"](
            record.project_id,
            primary_source_id="src1",
            secondary_source_id="src2",
            apply=True,
        )["ok"]
        is True
    )

    _adopt_job(record, foreign)
    broken = record.model_copy(update={"project_id": "not-a-uuid"})
    (Path(record.output) / "project_state.json").write_text(
        current.model_dump_json(), encoding="utf-8"
    )
    _adopt_job(broken, job)


def test_agent_helpers_empty_and_corrupt(tmp_path: Path, monkeypatch) -> None:
    from videoflow.mcp_server.agent_tools import _job, _state, _summary

    assert _summary(None) == {}
    empty_record, _ = init_project(output=tmp_path / "helper-empty")
    assert _state(empty_record) is not None
    (Path(empty_record.output) / "project_state.json").unlink()
    assert _state(empty_record) is not None
    from vf_shared.contracts.workspace import project_dir

    (project_dir(empty_record.project_id) / "state.json").unlink()
    (Path(empty_record.output) / "state.json").unlink()
    assert _state(empty_record) is None
    manager = FakeManager(None)
    try:
        _job(manager, empty_record.project_id)
    except Exception as exc:
        assert "no jobs" in str(exc)
