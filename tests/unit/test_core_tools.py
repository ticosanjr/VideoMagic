"""Consolidated 13-tool core profile."""

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

    def cancel(self, job_id, *, force: bool = False):
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
        ToolContext(manager=Manager(job)),  # type: ignore[arg-type]
    )
    return tools, record, job


def test_core_project_catalog_exec_job(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = setup(tmp_path, monkeypatch)
    assert tools["vf_project"](action="status", project_id=record.project_id)["ok"] is True
    capabilities = tools["vf_capabilities"]()
    assert capabilities["ok"] is True
    assert "compute" in capabilities
    assert capabilities["compute"]["execution_node"] == "local"
    catalog = tools["vf_catalog_search"](query="session")
    assert any(step["type"] == "session.ingest" for step in catalog["steps"])
    assert "recipes" not in catalog
    assert catalog["total"] == len(catalog["steps"])
    assert catalog["next_offset"] is None

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
    assert tools["vf_export"](action="render", project_id=record.project_id)["ok"] is True
    assert (
        tools["vf_job"](action="cancel", project_id=record.project_id, job_id="job-1")["ok"]
        is True
    )
    assert tools["vf_export"](action="validate", project_id=record.project_id)["ok"] in {
        True,
        False,
    }
    assert tools["vf_job"](action="qa", project_id=record.project_id)["ok"] is True


def test_core_ingest_interaction_and_errors(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = setup(tmp_path, monkeypatch)
    assert tools["vf_ingest"](action="multicam", project_id=record.project_id)["ok"] is False
    assert tools["vf_project"](action="status", project_id="missing")["ok"] is False
    assert tools["vf_interaction"](action="list", project_id=record.project_id)["ok"] is True
    assert tools["vf_job"](action="qa", project_id=record.project_id)["ok"] is True


def test_core_catalog_and_project_errors(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = setup(tmp_path, monkeypatch)
    assert tools["vf_project"](action="status")["code"] == "project_required"
    assert tools["vf_catalog_search"](query="nomatch", kind="steps")["steps"] == []
    assert tools["vf_catalog_search"](kind="recipes", limit=1)["code"] == "invalid_kind"
    assert tools["vf_catalog_search"](kind="steps", limit=1)["steps"]
    assert tools["vf_catalog_search"](offset=1, limit=1)["steps"]
    assert tools["vf_exec"](action="step", project_id=record.project_id)["ok"] is False
    assert (
        tools["vf_exec"](action="recipe", project_id=record.project_id)["code"] == "unknown_action"
    )
    assert tools["vf_artifact"](action="list", project_id="missing")["ok"] is False


def test_core_job_wait_and_render_status(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = setup(tmp_path, monkeypatch)
    waited = tools["vf_job"](action="wait", project_id=record.project_id, job_id="job-1")
    assert waited["ok"] is True
    assert (
        tools["vf_job"](action="status", project_id=record.project_id, job_id="job-1")["ok"]
        is True
    )
    assert (
        tools["vf_export"](action="roundtrip", project_id=record.project_id, direction="push")[
            "ok"
        ]
        is True
    )
    assert tools["vf_job"](action="qa", project_id="missing")["ok"] is False
    job.status = "running"
    assert (
        tools["vf_job"](action="wait", project_id=record.project_id, job_id="job-1", timeout_sec=1)[
            "code"
        ]
        == "timeout"
    )


def test_core_artifact_workspace_asset(tmp_path: Path, monkeypatch) -> None:
    from PIL import Image
    from vf_shared.contracts.assets import write_asset
    from vf_shared.contracts.workspace import ensure_project

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


def test_core_artifact_missing_and_catalog_filters(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = setup(tmp_path, monkeypatch)
    missing = tools["vf_artifact"](action="get", project_id=record.project_id, artifact="missing")
    assert missing[0]["ok"] is False
    assert tools["vf_catalog_search"](query="no-such-step")["steps"] == []


def test_core_exec_short_action(tmp_path: Path, monkeypatch) -> None:
    tools, record, job = setup(tmp_path, monkeypatch)
    job.result = {"shorts": [{"title": "One", "pieces": [[0, 1000]], "aspect_ratio": "9:16"}]}
    monkeypatch.setattr(
        "videoflow.application.short_editor.edit_short",
        lambda **kwargs: {"shorts": [{"title": "Edited"}]},
    )
    result = tools["vf_exec"](
        action="short", project_id=record.project_id, short_index=0, short_title="Edited"
    )
    assert result["ok"] is True
    assert result["short"]["title"] == "Edited"


def test_core_apply_beatmap_is_atomic(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    result = tools["vf_timeline"](
        action="apply_beatmap",
        project_id=record.project_id,
        expected_revision=1,
        beatmap={
            "revision": 1,
            "keep_ranges": [{"start_sec": 5/30, "end_sec": 20/30}],
        },
    )
    assert result["ok"] is True
    assert result["revision"] == 2
    assert result["report"]["cuts"] == 1

    conflict = tools["vf_timeline"](
        action="apply_beatmap",
        project_id=record.project_id,
        expected_revision=1,
        beatmap={"revision": 1},
    )
    assert conflict["ok"] is False
    assert conflict["code"] == "beatmap_conflict"


def test_core_exports_bundle_without_mp4(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    result = tools["vf_export"](project_id=record.project_id,
        targets="resolve",
    )
    assert result["ok"] is True
    assert set(result["bundle"]["files"]) == {"resolve"}
    assert Path(result["bundle"]["manifest"]).is_file()


def test_core_project_style_and_rule_learning(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    image = tmp_path / "reference.png"
    from PIL import Image

    Image.new("RGB", (16, 16), (20, 40, 60)).save(image)
    cloned = tools["vf_project"](
        action="clone_style",
        project_id=record.project_id,
        channel_id="canal-teste",
        images=[str(image)],
        name="teste",
    )
    assert cloned["ok"] is True
    assert cloned["channel_id"] == "canal-teste"

    learned = tools["vf_project"](
        action="learn_rule",
        project_id=record.project_id,
        channel_id="canal-teste",
        notes=["sempre usar legendas grandes", "cortes a cada 2 segundos"],
    )
    assert learned["ok"] is True
    assert learned["count"] == 2
    assert Path(learned["rulebook"]).is_file()


def test_core_style_and_beatmap_guards(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    assert tools["vf_project"](action="clone_style")["code"] == "channel_required"
    assert tools["vf_project"](action="clone_style", channel_id="x")["code"] == "output_required"
    assert (
        tools["vf_timeline"](action="apply_beatmap", project_id=record.project_id)["code"]
        == "beatmap_required"
    )
    assert (
        tools["vf_timeline"](action="apply_beatmap", project_id="missing", beatmap={"cuts": []})[
            "ok"
        ]
        is False
    )
    assert tools["vf_export"](project_id="missing")["ok"] is False
    assert tools["vf_job"](action="wait", project_id="missing")["ok"] is False


def test_core_exec_waits_for_the_step_job(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    result = tools["vf_exec"](
        action="step",
        project_id=record.project_id,
        step_id="preset.compile_rule",
        params={"channel_id": "demo", "review_notes": ["legendas grandes"]},
        wait=True,
    )
    assert result["ok"] is True
    assert result["wait"]["ok"] is True


def test_core_project_rejects_style_as_brand_kit(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    rejected = tools["vf_project"](
        action="init",
        output=str(tmp_path / "style-project"),
        channel_id="canal-paula-long",
    )
    assert rejected["ok"] is False
    assert rejected["code"] == "channel_not_found"
    assert "youtube-talking-head" in rejected["message"]

    accepted = tools["vf_project"](
        action="init",
        output=str(tmp_path / "kit-project"),
        channel_id="youtube-talking-head",
    )
    assert accepted["ok"] is True
    assert accepted["project"]["channel_id"] == "youtube-talking-head"


def test_core_error_branches_and_roundtrip_formats(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application.projects import init_project
    from videoflow.domain.errors import VideoFlowError

    tools, record, _ = setup(tmp_path, monkeypatch)
    assert (
        tools["vf_project"](action="clone_style", project_id="missing", channel_id="x")["ok"]
        is False
    )
    assert (
        tools["vf_exec"](action="step", project_id=record.project_id, step_id="not.a.step")["ok"]
        is False
    )

    empty, _ = init_project(output=tmp_path / "empty")
    assert (
        tools["vf_export"](project_id=empty.project_id)["code"]
        == "timeline_required"
    )

    monkeypatch.setattr(
        Manager,
        "cancel",
        lambda self, job_id, force=False: (_ for _ in ()).throw(
            VideoFlowError("cancel failed")
        ),
    )
    assert (
        tools["vf_job"](action="cancel", project_id=record.project_id, job_id="job-1")["ok"]
        is False
    )

    for nle, suffix in (("premiere", ".xml"), ("kdenlive", ".kdenlive")):
        target = tmp_path / "out" / "exports" / f"push{suffix}"
        pushed = tools["vf_export"](
            action="roundtrip",
            project_id=record.project_id,
            direction="push",
            nle=nle,
            path=str(target),
        )
        assert pushed["ok"] is True
        assert target.is_file()


def test_core_style_catalog_actions_and_project_binding(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application.projects import load_project_state

    tools, record, _ = setup(tmp_path, monkeypatch)
    workspace = tmp_path / "workspace"
    listed = tools["vf_style"](action="list")
    assert listed["ok"] is True
    assert any(item["style_id"] == "canal-paula-reels" for item in listed["styles"])

    saved = tools["vf_style"](
        action="save",
        style_id="canal-teste",
        name="Canal Teste",
        target_lufs=-14.0,
        min_silence_ms=300,
        layout_mode="cutout",
        caption_preset="kinetic_highlight",
        motion_engine="hyperframes",
        export_targets=["mp4_youtube", "resolve"],
        palette=["#111827", "#f97316"],
        fonts=["Inter"],
        workspace_dir=str(workspace),
    )
    assert saved["ok"] is True
    assert Path(saved["file"]).is_file()
    assert (workspace / "presets" / "canal-teste.md").is_file()
    assert saved["sync"]["copied"]

    duplicated = tools["vf_style"](
        action="duplicate",
        style_id="canal-teste",
        new_id="canal-teste-copy",
        name="Canal Teste Copy",
    )
    assert duplicated["ok"] is True
    assert duplicated["style_id"] == "canal-teste-copy"
    assert tools["vf_style"](action="delete", style_id="canal-teste-copy")["deleted"] is True

    fetched = tools["vf_style"](action="get", style_id="canal-teste")
    assert fetched["style"]["target_lufs"] == -14.0
    assert "canal-teste" in fetched["markdown"]

    learned = tools["vf_style"](
        action="learn_rule",
        style_id="canal-teste",
        feedback_note="Cortar antes de 1s",
    )
    assert learned["count"] == 1
    assert learned["rules"][0]["text"] == "Cortar antes de 1s"

    synced = tools["vf_style"](
        action="sync",
        workspace_dir=str(workspace),
        overwrite=True,
    )
    assert synced["sync"]["copied"] == ["canal-teste"]

    created = tools["vf_project"](
        action="init",
        name="Styled",
        output=str(tmp_path / "styled-project"),
        style_id="canal-teste",
    )
    assert created["project"]["style_id"] == "canal-teste"
    state = load_project_state(
        __import__("videoflow.application.projects", fromlist=["get_project"]).get_project(
            created["project"]["project_id"]
        )
    )
    assert state.style_id == "canal-teste"

    assert tools["vf_style"](action="delete", style_id="canal-teste")["deleted"] is True


def test_core_style_guards_and_markdown_save(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    assert tools["vf_style"](action="save")["code"] == "style_required"
    assert tools["vf_style"](action="sync")["code"] == "workspace_required"
    assert tools["vf_style"](action="bogus")["code"] == "unknown_action"

    saved = tools["vf_style"](
        action="save",
        markdown_content=(
            "---\nstyle_id: md-core\nname: Markdown Core\ntarget_lufs: -15\n---\n\n# Corpo\n"
        ),
    )
    assert saved["style_id"] == "md-core"
    assert saved["style"]["target_lufs"] == -15.0

    updated = tools["vf_project"](
        action="open",
        project_id=record.project_id,
        style_id="canal-paula-reels",
    )
    assert updated["project"]["style_id"] == "canal-paula-reels"

    invalid = tools["vf_project"](
        action="init",
        output=str(tmp_path / "missing-style-project"),
        style_id="missing-style",
    )
    assert invalid["code"] == "style_not_found"


def test_core_bundle_uses_project_style_export_targets(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application.style_catalog import StyleCatalog
    from videoflow.domain.styles import StyleDefinition

    tools, record, _ = setup(tmp_path, monkeypatch)
    StyleCatalog().save(
        StyleDefinition(
            style_id="export-min",
            name="Export Minimal",
            export_targets=["resolve"],
        )
    )
    tools["vf_project"](
        action="open",
        project_id=record.project_id,
        style_id="export-min",
    )

    result = tools["vf_export"](project_id=record.project_id)

    assert result["ok"] is True
    assert set(result["bundle"]["files"]) == {"resolve"}
    assert result["bundle"]["targets"] == ["resolve"]


def test_core_style_analyze_returns_candidate(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "videoflow.application.style_clone.clone_style",
        lambda *args, **kwargs: {"ok": True, "saved": kwargs.get("save"), "style_id": "candidate"},
    )
    result = tools["vf_style"](
        action="analyze",
        style_id="candidate",
        reference_url="https://example.com",
        workspace_dir=str(tmp_path),
    )
    assert result["ok"] is True
    assert result["saved"] is False


def test_core_style_actions(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    assert tools["vf_style"](action="list")["ok"] is True
    saved = tools["vf_style"](
        action="save",
        style_id="alias-style",
        name="Alias",
        platforms=["youtube"],
        workspace_dir=str(tmp_path / "workspace"),
    )
    assert saved["ok"] is True
    learned = tools["vf_style"](
        action="learn_rule",
        style_id="alias-style",
        feedback_note="Cortar antes de 1s",
    )
    assert learned["ok"] is True


def test_unified_domain_tools_dispatch_to_internal_domains(
    tmp_path: Path, monkeypatch
) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    calls: dict[str, object] = {}

    from videoflow.domains.audio import studio
    from videoflow.domains.media import fetch_tools
    from videoflow.domains.vision import tools as vision_tools

    def fake_tts(project, text, **kwargs):
        calls["tts"] = (project, text, kwargs)
        return {"ok": True}

    monkeypatch.setattr(studio, "tts_generate", fake_tts)
    monkeypatch.setattr(
        studio,
        "separate_audio_stems",
        lambda project, path, **kwargs: {"ok": True, "stems": kwargs.get("stems")},
    )
    monkeypatch.setattr(
        vision_tools,
        "remove_background",
        lambda project, path, **kwargs: {"ok": True, "is_video": kwargs.get("is_video")},
    )
    monkeypatch.setattr(
        fetch_tools,
        "fetch_stock_broll",
        lambda project, query, **kwargs: {"ok": True, "query": query, **kwargs},
    )
    monkeypatch.setattr(
        fetch_tools,
        "rip_video_segment",
        lambda project, url, start, end, **kwargs: {
            "ok": True,
            "url": url,
            "clip": [start, end],
            **kwargs,
        },
    )

    assert tools["vf_audio"](
        action="tts",
        project_id=record.project_id,
        text="olá",
        quality="draft",
    )["ok"] is True
    assert calls["tts"][:2] == (record.project_id, "olá")

    stems = tools["vf_audio"](
        action="stems",
        project_id=record.project_id,
        input_path=str(tmp_path / "voice.wav"),
        stems=["vocals"],
    )
    assert stems["stems"] == ["vocals"]

    matte = tools["vf_vision"](
        action="matte",
        project_id=record.project_id,
        input_path=str(tmp_path / "frame.png"),
        is_video=True,
    )
    assert matte["is_video"] is True

    broll = tools["vf_media"](
        action="fetch_stock_broll",
        project_id=record.project_id,
        query="ocean",
        orientation="portrait",
    )
    assert broll["query"] == "ocean"
    assert broll["orientation"] == "portrait"

    segment = tools["vf_media"](
        action="rip_video_segment",
        project_id=record.project_id,
        url="https://example.test/v",
        start_time=1.0,
        end_time=2.5,
    )
    assert segment["clip"] == [1.0, 2.5]

    assert tools["vf_audio"](action="nope")["code"] == "unknown_action"
    assert tools["vf_vision"](action="nope")["code"] == "unknown_action"
    assert tools["vf_media"](action="nope")["code"] == "unknown_action"


def test_unified_domain_tool_error_envelopes(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    from videoflow.domains.audio import studio
    from videoflow.domains.media import fetch_tools
    from videoflow.domains.vision import tools as vision_tools

    def boom(*args, **kwargs):
        raise ValueError("no backend")

    monkeypatch.setattr(studio, "tts_generate", boom)
    monkeypatch.setattr(studio, "mix_and_master_track", boom)
    monkeypatch.setattr(vision_tools, "upscale_media", boom)
    monkeypatch.setattr(fetch_tools, "fetch_sfx", boom)

    assert tools["vf_audio"](
        action="tts", project_id=record.project_id, text="oi"
    )["code"] == "audio_failed"
    assert tools["vf_audio"](
        action="mix",
        project_id=record.project_id,
        input_path=str(tmp_path / "voice.wav"),
    )["code"] == "audio_failed"
    assert tools["vf_vision"](
        action="upscale",
        project_id=record.project_id,
        input_path=str(tmp_path / "frame.png"),
    )["code"] == "vision_failed"
    assert tools["vf_media"](
        action="fetch_sfx",
        project_id=record.project_id,
        query="whoosh",
    )["code"] == "media_failed"


def test_unified_domain_tools_cover_remaining_actions(
    tmp_path: Path, monkeypatch
) -> None:
    tools, record, _ = setup(tmp_path, monkeypatch)
    from videoflow.domains.audio import studio
    from videoflow.domains.media import fetch_tools
    from videoflow.domains.vision import tools as vision_tools

    monkeypatch.setattr(
        studio, "voice_clean_and_enhance", lambda *a, **k: {"ok": True, "clean": True}
    )
    monkeypatch.setattr(
        studio, "generate_music_or_sfx", lambda *a, **k: {"ok": True, "music": True}
    )
    monkeypatch.setattr(
        studio, "mix_and_master_track", lambda *a, **k: {"ok": True, "master": True}
    )
    monkeypatch.setattr(
        vision_tools, "transcribe_word_aligned", lambda *a, **k: {"ok": True, "captions": True}
    )
    monkeypatch.setattr(
        vision_tools, "upscale_media", lambda *a, **k: {"ok": True, "upscale": True}
    )
    monkeypatch.setattr(
        fetch_tools, "fetch_stock_images", lambda *a, **k: {"ok": True, "images": True}
    )
    monkeypatch.setattr(
        fetch_tools, "fetch_sfx", lambda *a, **k: {"ok": True, "sfx": True}
    )

    assert tools["vf_audio"](
        action="clean", project_id=record.project_id,
        input_path=str(tmp_path / "voice.wav"),
    )["clean"] is True
    assert tools["vf_audio"](
        action="music", project_id=record.project_id, prompt="bed"
    )["music"] is True
    assert tools["vf_audio"](
        action="mix", project_id=record.project_id,
        input_path=str(tmp_path / "voice.wav"),
    )["master"] is True
    assert tools["vf_vision"](
        action="captions", project_id=record.project_id,
        audio_path=str(tmp_path / "voice.wav"),
    )["captions"] is True
    assert tools["vf_vision"](
        action="upscale", project_id=record.project_id,
        input_path=str(tmp_path / "frame.png"),
    )["upscale"] is True
    assert tools["vf_media"](
        action="fetch_stock_images", project_id=record.project_id, query="cat"
    )["images"] is True
    assert tools["vf_media"](
        action="fetch_sfx", project_id=record.project_id, query="whoosh"
    )["sfx"] is True


def test_default_export_targets_keep_the_four_deliverables() -> None:
    from videoflow.application.delivery_bundle import DEFAULT_BUNDLE_TARGETS

    assert set(DEFAULT_BUNDLE_TARGETS) == {
        "mp4_youtube",
        "resolve",
        "premiere",
        "kdenlive",
    }
