"""v4.6 MCP fail-closed contracts, workspace paths, clones, and keyless fallbacks."""

from __future__ import annotations

import os
import wave
from pathlib import Path

import httpx

from videoflow.application.projects import (
    clone_project,
    delete_project,
    init_project,
    save_project_state,
)
from videoflow.domain.state import MediaInfo
from videoflow.mcp_server.context import ToolContext
from videoflow.mcp_server.core_tools import register_core_tools

RATE = 48_000


class Telemetry:
    def logs(self, **kwargs):
        return []

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
    def __init__(self, job: Job):
        self.job = job

    def get(self, job_id):
        return self.job

    def list(self):
        return [self.job]

    def start(self, *args, **kwargs):
        return self.job

    def cancel(self, job_id, *, force: bool = False):
        return self.job

    def update_result(self, job_id, result):
        self.job.result = result


def _wav(path: Path, seconds: float = 0.05) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(b"\x00\x00" * int(RATE * seconds))
    return path


def setup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    record, state = init_project(
        project_id="demo",
        name="Demo",
        output=tmp_path / "demo",
    )
    monkeypatch.setenv("VF_PROJECT_OUTPUT", str(record.output))
    media = MediaInfo(
        source_path=str(source),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=RATE,
    )
    state = state.model_copy(
        update={
            "sources": {"src1": media},
            "primary_source_id": "src1",
            "media_info": media,
        }
    )
    save_project_state(record, state, bump_revision=False)
    job = Job(Path(record.output), record.project_id)
    tools: dict[str, object] = {}

    def register(func):
        tools[func.__name__] = func
        return func

    register_core_tools(register, ToolContext(manager=Manager(job)))  # type: ignore[arg-type]
    return tools, record, job


def test_unknown_project_action_fails_closed(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    result = tools["vf_project"](action="inexistente", project_id=record.project_id)
    assert result["ok"] is False
    assert result["error_code"] == "unknown_action"
    assert "status" in result["valid_actions"]
    assert "init" in result["valid_actions"]
    assert "Valid actions" in result["fix_hint"]


def test_unknown_ingest_action_fails_closed(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    result = tools["vf_ingest"](action="inexistente", project_id=record.project_id)
    assert result["ok"] is False
    assert result["error_code"] == "unknown_action"
    assert set(result["valid_actions"]) == {"session", "multicam", "diagnose", "probe"}


def test_music_action_attaches_a_local_track(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    track = _wav(tmp_path / "track.wav")
    result = tools["vf_audio"](
        action="music",
        project_id=record.project_id,
        music_path=str(track),
    )
    assert result["ok"] is True
    output = Path(str(result["output"]))
    assert output.is_file()
    assert output.name == "music.wav"
    assert output.read_bytes()[:4] == b"RIFF"
    assert result["mode"] == "local"


def test_media_search_alias_uses_keyless_stock_search(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    from videoflow.domains.media import fetch_tools

    captured: dict[str, object] = {}

    def fake_images(project_id, query, **kwargs):
        captured.update(project_id=project_id, query=query, **kwargs)
        return {"ok": True, "images": [query]}

    monkeypatch.setattr(fetch_tools, "fetch_stock_images", fake_images)
    result = tools["vf_media"](
        action="search",
        project_id=record.project_id,
        query="ocean",
        count=3,
    )
    assert result["ok"] is True
    assert captured["query"] == "ocean"
    assert captured["count"] == 3


def test_ingest_probe_returns_ffprobe_metadata(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    import videoflow.adapters.ffmpeg as ffmpeg_module

    source = tmp_path / "source.mp4"

    class FakeAdapter:
        def probe(self, path: Path) -> MediaInfo:
            return MediaInfo(
                source_path=str(path),
                duration_frames=90,
                fps_num=30,
                fps_den=1,
                width=1280,
                height=720,
                audio_sample_rate=RATE,
            )

    monkeypatch.setattr(ffmpeg_module, "FFmpegAdapter", FakeAdapter)
    result = tools["vf_ingest"](
        action="probe",
        project_id=record.project_id,
        sources=[str(source)],
    )
    assert result["ok"] is True
    assert result["probe"]["duration_frames"] == 90
    assert result["probe"]["width"] == 1280


def test_workspace_root_never_nests_projects_twice(tmp_path: Path) -> None:
    from videoflow.domains.media.fetch_workspace import Workspace

    projects = Workspace("demo", root=tmp_path / "projects")
    assert projects.root == (tmp_path / "projects" / "demo").resolve()
    workspace = Workspace("demo", root=tmp_path / "workspace")
    assert workspace.root == (tmp_path / "workspace" / "projects" / "demo").resolve()


def test_install_model_invalidates_the_capability_cache(
    tmp_path: Path, monkeypatch
) -> None:
    from videoflow.application import models

    monkeypatch.setenv("VIDEOWFLOW_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    target = tmp_path / "models" / "whisper" / "ggml-tiny.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"model")
    calls: list[bool] = []
    monkeypatch.setattr(models, "clear_capability_cache", lambda: calls.append(True))
    result = models.install_model("whisper-tiny")
    assert result["installed"] is True
    assert calls


def test_models_install_command_exits_zero_when_installed(monkeypatch) -> None:
    from videoflow import cli

    monkeypatch.setattr(cli, "installed_path", lambda model_id: None)
    monkeypatch.setattr(
        cli,
        "install_model",
        lambda model_id, **kwargs: {"id": model_id, "installed": True, "path": "/tmp/model"},
    )
    monkeypatch.setattr(cli, "invalidate_model_cache", lambda: None)
    assert cli._install_asr_model("faster-whisper-small") == 0


def test_clone_auto_suffixes_and_never_shares_work_files(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    record, state = init_project(
        project_id="demo",
        name="Demo",
        output=tmp_path / "demo",
    )
    pcm = _wav(tmp_path / "demo" / "work" / "pcm.wav")
    state = state.model_copy(
        update={"pipeline": state.pipeline.model_copy(update={"pcm_path": str(pcm)})}
    )
    save_project_state(record, state, bump_revision=False)

    first, first_state = clone_project(record)
    second, _second_state = clone_project(record)

    assert Path(first.output).name == "demo-copy"
    assert Path(second.output).name == "demo-copy-2"
    cloned_pcm = Path(first_state.pipeline.pcm_path)
    assert cloned_pcm.is_file()
    assert cloned_pcm.is_relative_to(Path(first.output))
    assert cloned_pcm != pcm

    delete_project(first, force=True)
    assert pcm.is_file()
    assert pcm.read_bytes()[:4] == b"RIFF"


def test_keyless_video_search_uses_wikimedia_without_api_keys(tmp_path: Path) -> None:
    from videoflow.domains.media.fetch_service import FetchService

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "commons.wikimedia.org":
            return httpx.Response(
                200,
                json={
                    "query": {
                        "pages": {
                            "1": {
                                "pageid": 1,
                                "title": "File:Ocean.webm",
                                "imageinfo": [
                                    {
                                        "url": "https://upload.wikimedia.org/ocean.webm",
                                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Ocean.webm",
                                        "extmetadata": {
                                            "LicenseShortName": {"value": "CC0"},
                                            "Artist": {"value": "Ada"},
                                        },
                                    }
                                ],
                            }
                        }
                    }
                },
            )
        if request.url.host == "upload.wikimedia.org":
            return httpx.Response(200, content=b"webm-bytes")
        return httpx.Response(404, json={})

    service = FetchService(
        workspace_root=tmp_path,
        transport=httpx.MockTransport(handler),
        env={},
    )
    result = service.fetch_stock_broll("demo", "ocean", min_duration=0)
    assert result["ok"] is True
    assert result["provider"] == "wikimedia"
    path = Path(result["assets"][0]["path"])
    assert path.is_file()
    assert path.read_bytes() == b"webm-bytes"


def test_procedural_sfx_fallback_writes_a_real_wav(tmp_path: Path) -> None:
    from videoflow.domains.media.fetch_service import FetchService

    service = FetchService(
        workspace_root=tmp_path,
        transport=httpx.MockTransport(lambda request: httpx.Response(404)),
        env={},
    )
    result = service.fetch_sfx("demo", "impact boom")
    assert result["ok"] is True
    assert result["provider"] == "procedural"
    path = Path(result["assets"][0]["path"])
    assert path.is_file()
    assert path.read_bytes()[:4] == b"RIFF"
    assert path.parent.name == "sfx"


def test_project_output_dir_deduplicates_an_existing_projects_path(tmp_path: Path) -> None:
    from videoflow.application.projects import project_output_dir

    assert project_output_dir("demo", base=tmp_path / "projects") == tmp_path / "projects" / "demo"
    assert project_output_dir("demo", tmp_path / "workspace") == tmp_path / "workspace"
    assert (
        project_output_dir("demo", tmp_path / "projects" / "demo")
        == tmp_path / "projects" / "demo"
    )
    assert os.path.sep  # keeps the import meaningful on every platform


def test_unknown_job_and_exec_actions_are_fail_closed(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    for name, arguments in (
        ("vf_job", {"action": "nexus"}),
        ("vf_exec", {"action": "nexus", "project_id": record.project_id}),
        ("vf_timeline", {"action": "nexus", "project_id": record.project_id}),
    ):
        result = tools[name](**arguments)
        assert result["ok"] is False
        assert result["error_code"] == "unknown_action"
        assert result["valid_actions"]
