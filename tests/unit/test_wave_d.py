from __future__ import annotations

from pathlib import Path

from videoflow.application.audio_synthesis import compose_music
from videoflow.core.context import PipelineContext
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.steps.audio_synth import AudioMixStep, MixParams
from videoflow.steps.base import StepIO


def test_workspace_root_accepts_projects_directory(tmp_path: Path, monkeypatch) -> None:
    from vf_contracts.workspace import project_dir, workspace_root

    monkeypatch.setenv("VF_WORKSPACE_ROOT", str(tmp_path / "workspace" / "projects"))
    assert workspace_root() == tmp_path / "workspace" / "projects"
    assert project_dir("p1") == tmp_path / "workspace" / "projects" / "p1"


def test_domain_storage_projects_root_does_not_duplicate(tmp_path: Path, monkeypatch) -> None:
    from videoflow_mcp_audio import storage as audio_storage
    from videoflow_mcp_vision import storage as vision_storage

    monkeypatch.setattr(audio_storage, "_shared_project_dir", lambda project_id: None)
    monkeypatch.setattr(vision_storage, "_shared_project_dir", lambda project_id: None)
    root = tmp_path / "workspace"
    (root / "projects").mkdir(parents=True)
    old = {
        key: __import__("os").environ.get(key) for key in ("VF_PROJECTS_ROOT", "VF_WORKSPACE_ROOT")
    }
    try:
        __import__("os").environ["VF_PROJECTS_ROOT"] = str(root)
        assert audio_storage.project_dir("p1") == root / "projects" / "p1"
        assert vision_storage.project_dir("p1") == root / "projects" / "p1"
        __import__("os").environ["VF_PROJECTS_ROOT"] = str(root / "projects")
        assert audio_storage.project_dir("p1") == root / "projects" / "p1"
    finally:
        for key, value in old.items():
            if value is None:
                __import__("os").environ.pop(key, None)
            else:
                __import__("os").environ[key] = value


def test_compose_music_reports_generated_and_loop(tmp_path: Path) -> None:
    payload = compose_music(tmp_path, duration_sec=1.5, sample_rate=8000)
    assert payload["generated_sec"] == 1.5
    assert payload["auto_looped"] is False
    looped = compose_music(
        tmp_path / "loop", duration_sec=5.0, sample_rate=8000, max_loop_seconds=1.0
    )
    assert looped["generated_sec"] == 1.0
    assert looped["auto_looped"] is True
    assert looped["loop_seconds"] == 1.0


def test_audio_mix_three_act_uses_timeline_duration(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=300,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )
    state = ProjectState(
        media_info=media,
        sources={"primary": media},
        primary_source_id="primary",
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_id="primary",
                source_in_frame=0,
                source_out_frame=3600,
                timeline_in_frame=0,
                timeline_out_frame=3600,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_id="primary",
                source_in_sample=0,
                source_out_sample=5_760_000,
                timeline_in_sample=0,
                timeline_out_sample=5_760_000,
            )
        ],
    )
    context = PipelineContext(
        source=source,
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        media=media,
        state=state,
    )
    master = context.output / "audio" / "master.wav"
    master.parent.mkdir(parents=True)
    master.write_bytes(b"wav")
    music = tmp_path / "music.wav"
    music.write_bytes(b"music")
    context.artifacts["audio_master"] = str(master)
    captured: list[str] = []

    def fake_run(command, **kwargs):
        captured.append(" ".join(command))
        Path(command[-1]).write_bytes(b"mixed")
        return type("Done", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr("videoflow.steps.audio_synth.find_binary", lambda name: "ffmpeg")
    monkeypatch.setattr("videoflow.steps.audio_synth.subprocess.run", fake_run)
    AudioMixStep().run(
        context,
        MixParams(music_arc="three_act", music_path=str(music), target_lufs=-16.0),
        StepIO(),
    )
    filters = next(item for item in captured if "volume='if(lt(t," in item)
    assert "if(lt(t,24.000" in filters
    assert "if(lt(t,96.000" in filters


def test_vf_ingest_payload_shape(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application.jobs import JobManager
    from videoflow.application.projects import init_project, save_project_state
    from videoflow.engine.batch import BatchManager
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    record, _ = init_project(name="Ingest payload", output=tmp_path / "ingest")
    state = ProjectState(
        media_info=MediaInfo(
            source_path=str(tmp_path / "source.mp4"),
            duration_frames=300,
            fps_num=30,
            fps_den=1,
            width=320,
            height=240,
            audio_sample_rate=48000,
        ),
        sources={
            "primary": MediaInfo(
                source_path=str(tmp_path / "source.mp4"),
                duration_frames=300,
                fps_num=30,
                fps_den=1,
                width=320,
                height=240,
                audio_sample_rate=48000,
            )
        },
        primary_source_id="primary",
    )
    save_project_state(record, state, bump_revision=False)
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager, batch_manager=BatchManager(manager)),
    )
    assert tools["vf_ingest"](action="multicam", project_id="missing")["ok"] is False

    from videoflow.application.jobs import Job

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    monkeypatch.setattr(
        manager,
        "start",
        lambda *args, **kwargs: Job(source=source, output=Path(record.output), options={}),
    )
    response = tools["vf_ingest"](
        action="session",
        project_id=record.project_id,
        sources=[str(source)],
    )
    assert response["ok"] is True
    assert response["mode"] == "session"
    assert response["step_type"] == "session.ingest"
    assert response["source_duration_sec"] == 10.0
    assert response["cfr_fps"] == 30.0
    assert "pcm_path" in response and "audio_offset_ms" in response


def test_runtime_cache_and_model_paths(tmp_path: Path, monkeypatch) -> None:
    from videoflow.runtime import cache_root, model_search_dirs

    monkeypatch.setenv("VF_CACHE_DIR", str(tmp_path / "cache"))
    assert cache_root() == tmp_path / "cache"
    monkeypatch.delenv("VF_CACHE_DIR", raising=False)
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    assert cache_root() == tmp_path / "home" / "cache"
    paths = model_search_dirs()
    assert (tmp_path / "home" / "models") in paths


def test_overlay_source_time_and_plan_no_media(tmp_path: Path) -> None:
    from videoflow.application.beatmap_plan import build_beatmap_plan
    from videoflow.application.overlays import add_overlay
    from videoflow.application.projects import init_project, save_project_state
    from videoflow.domain.styles import StyleDefinition

    plan = build_beatmap_plan(ProjectState(), StyleDefinition(style_id="empty", name="Empty"))
    assert plan["warnings"]

    record, _ = init_project(name="Overlay source", output=tmp_path / "overlay-source")
    state = ProjectState(
        media_info=MediaInfo(
            source_path=str(tmp_path / "source.mp4"),
            duration_frames=300,
            fps_num=30,
            fps_den=1,
            width=320,
            height=240,
            audio_sample_rate=48000,
        )
    )
    state = state.model_copy(
        update={
            "sources": {"primary": state.media_info},
            "primary_source_id": "primary",
            "video_segments": [
                VideoSegment(
                    clip_id="v1",
                    source_id="primary",
                    source_in_frame=0,
                    source_out_frame=300,
                    timeline_in_frame=0,
                    timeline_out_frame=300,
                )
            ],
        }
    )
    (tmp_path / "source.mp4").write_bytes(b"x")
    save_project_state(record, state, bump_revision=False)
    asset = tmp_path / "logo.png"
    asset.write_bytes(b"x")
    result = add_overlay(record.project_id, str(asset), at_source_sec=1.0)
    assert result["overlay"]["start_frame"] == 30
