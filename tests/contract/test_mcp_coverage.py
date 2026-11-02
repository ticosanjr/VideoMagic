from __future__ import annotations

import asyncio
import time
from pathlib import Path

from tests.contract.test_api_timeline import _client
from videoflow.domain.state import ProjectState
from videoflow.mcp_server import server as server_module
from videoflow.mcp_server.server import build_server


def call(server, name: str, arguments: dict | None = None) -> dict:
    async def run() -> dict:
        result = await server.call_tool(name, arguments or {})
        return result.structured_content  # type: ignore[attr-defined]

    return asyncio.run(run())


def _setup(monkeypatch, tmp_path: Path):
    from videoflow.adapters.ffmpeg import FFmpegAdapter

    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    client, manager = _client(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    monkeypatch.setattr(FFmpegAdapter, "probe", lambda self, path: _media(Path(path)))
    server = build_server(manager)
    loaded = call(server, "videoflow_load_media", {"file_path": str(source)})
    assert loaded["ok"] is True, loaded
    job = manager.start(source, tmp_path / "out", options={}, queue=True)
    server.videoflow_last.update(  # type: ignore[attr-defined]
        source=source, output=job.output, job_id=str(job.job_id)
    )
    for _ in range(200):
        if job.status in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.01)
    state = ProjectState.model_validate_json(
        (tmp_path / "out" / "project_state.json").read_text()
        if (tmp_path / "out" / "project_state.json").is_file()
        else _state_json(source)
    )
    state.transcript = [
        __import__("videoflow.domain.state", fromlist=["Sentence"]).Sentence(
            id=0, start_sample=0, end_sample=48000, text="This is the hook?", speaker=0
        ),
        __import__("videoflow.domain.state", fromlist=["Sentence"]).Sentence(
            id=1, start_sample=48000, end_sample=96000, text="Here is the result.", speaker=0
        ),
    ]
    (job.output / "project_state.json").write_text(state.model_dump_json(), encoding="utf-8")
    short_path = job.output / "short-1.mp4"
    short_path.write_bytes(b"short")
    thumb = job.output / "thumb-1.png"
    thumb.write_bytes(b"png")
    job.result = {
        "ok": True,
        "artifacts": {"final.mp4": str(job.output / "final.mp4")},
        "shorts": [
            {"title": "Hook", "path": str(short_path), "thumbnail": str(thumb), "score": 80}
        ],
        "broll_plan": {"Short 1": [{"path": str(short_path)}]},
    }
    (job.output / "final.mp4").write_bytes(b"mp4")
    (job.output / "review.json").write_text('{"checks": []}', encoding="utf-8")
    return client, manager, server, job, source


def _media(path: Path):
    from videoflow.domain.state import MediaInfo

    return MediaInfo(
        source_path=str(path),
        duration_frames=90,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=48000,
    )


def _state_json(source: Path) -> str:
    from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment

    return ProjectState(
        media_info=MediaInfo(
            source_path=str(source),
            duration_frames=90,
            fps_num=30,
            fps_den=1,
            width=640,
            height=360,
            audio_sample_rate=48000,
        ),
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_in_frame=0,
                source_out_frame=90,
                timeline_in_frame=0,
                timeline_out_frame=90,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_in_sample=0,
                source_out_sample=144000,
                timeline_in_sample=0,
                timeline_out_sample=144000,
            )
        ],
    ).model_dump_json()


def test_mcp_read_and_admin_tools(monkeypatch, tmp_path: Path) -> None:
    _client_obj, manager, server, job, source = _setup(monkeypatch, tmp_path)
    job_id = str(job.job_id)

    for name, args in [
        ("videoflow_run_vad", {"noise_db": 0}),
        ("videoflow_transcribe", {"language": "xx"}),
        ("videoflow_import_url", {"url": "not-a-url"}),
        (
            "videoflow_export_fcpxml",
            {"output_path": str(tmp_path / "x.fcpxml"), "target_nle": "bad"},
        ),
        ("videoflow_list_publish_targets", {}),
        ("videoflow_list_publish_queue", {}),
        ("videoflow_list_project_templates", {}),
        ("videoflow_list_brand_templates", {}),
        ("videoflow_list_fonts", {}),
        ("videoflow_list_music", {}),
        ("videoflow_list_images", {}),
        ("videoflow_list_providers", {}),
        ("videoflow_list_schedules", {}),
        ("videoflow_list_jobs", {}),
        ("videoflow_list_models", {}),
        ("videoflow_list_plugins", {}),
        ("videoflow_list_steps", {}),
        ("videoflow_list_recipes", {}),
        ("videoflow_cost_metrics", {}),
        ("videoflow_get_job", {"job_id": job_id}),
        ("videoflow_get_timeline", {"job_id": job_id}),
        ("videoflow_list_clip_comments", {"job_id": job_id}),
        ("videoflow_validate_exports", {"job_id": job_id}),
        ("videoflow_list_capabilities", {}),
        ("videoflow_render_frame", {"time_sec": 1.0, "job_id": job_id}),
        ("videoflow_create_backup", {}),
        ("videoflow_reload_plugins", {}),
        ("videoflow_get_recipe", {"recipe_id": "youtube_talking_head"}),
        ("videoflow_export_config", {"options": {"crf": 18}}),
        ("videoflow_import_config", {"schema_version": 1, "options": {}}),
        ("videoflow_get_batch", {"batch_id": "missing"}),
        ("videoflow_cancel_batch", {"batch_id": "missing"}),
        ("videoflow_run_schedule", {"schedule_id": "missing"}),
        ("videoflow_pause_job", {"job_id": job_id}),
        ("videoflow_unpause_job", {"job_id": job_id}),
        ("videoflow_set_job_priority", {"job_id": job_id, "priority": 3}),
        ("videoflow_cancel_job", {"job_id": job_id}),
        ("videoflow_set_plugin_enabled", {"plugin_id": "missing", "enabled": False}),
    ]:
        payload = call(server, name, args)
        assert isinstance(payload, dict), name

    saved_target = call(
        server,
        "videoflow_save_publish_target",
        {"name": "demo", "webhook_url": "http://127.0.0.1:9/hook", "enabled": False},
    )
    assert saved_target["ok"] is True
    saved_template = call(
        server,
        "videoflow_save_project_template",
        {"name": "demo", "template": {"name": "demo", "options": {}}},
    )
    assert saved_template["ok"] is True
    saved_brand = call(
        server,
        "videoflow_save_brand_template",
        {"name": "demo", "template": {"name": "demo"}},
    )
    assert saved_brand["ok"] is True
    saved_schedule = call(
        server,
        "videoflow_save_schedule",
        {
            "schedule": {
                "id": "demo",
                "source": str(source),
                "output": str(tmp_path / "sched"),
                "recipe_id": "youtube_talking_head",
            }
        },
    )
    assert saved_schedule["ok"] is True
    assert call(server, "videoflow_list_schedules", {})["ok"] is True

    recipe = {
        "schema_version": 1,
        "id": "mcp_demo",
        "name": "MCP demo",
        "steps": [{"id": "ingest", "type": "ingest", "params": {}}],
    }
    assert call(server, "videoflow_validate_recipe", {"recipe": recipe})["ok"] is True
    assert call(server, "videoflow_save_recipe", {"recipe": recipe})["ok"] is True


def test_mcp_timeline_short_and_run_tools(monkeypatch, tmp_path: Path) -> None:
    _client_obj, manager, server, job, source = _setup(monkeypatch, tmp_path)
    job_id = str(job.job_id)

    assert (
        call(
            server,
            "videoflow_edit_timeline",
            {"clip_id": "v1", "action": "move", "delta_sec": 0.1, "job_id": job_id},
        )["ok"]
        is True
    )
    overlay = call(
        server,
        "videoflow_add_timeline_overlay",
        {
            "path": str(job.output / "final.mp4"),
            "start_sec": 0.1,
            "duration_sec": 0.2,
            "job_id": job_id,
        },
    )
    assert overlay["ok"] is True
    overlay_id = overlay["overlay"]["overlay_id"]
    assert (
        call(
            server,
            "videoflow_remove_timeline_overlay",
            {"overlay_id": overlay_id, "job_id": job_id},
        )["ok"]
        is True
    )
    comment = call(
        server, "videoflow_add_clip_comment", {"clip_id": "v1", "text": "tighten", "job_id": job_id}
    )
    assert comment["ok"] is True
    comment_id = comment["comment"]["id"]
    assert (
        call(server, "videoflow_remove_clip_comment", {"comment_id": comment_id, "job_id": job_id})[
            "ok"
        ]
        is True
    )
    assert (
        call(
            server,
            "videoflow_approve_broll",
            {"title": "Short 1", "approved": [0], "job_id": job_id},
        )["ok"]
        is True
    )
    assert (
        call(server, "videoflow_decide_review", {"approved": True, "job_id": job_id})["ok"] is True
    )

    assert call(server, "videoflow_generate_shorts", {"count": 1, "min_count": 1})["ok"] is True
    assert call(server, "videoflow_edit_short", {"index": 0, "title": "New"})["ok"] in {True, False}
    assert call(server, "videoflow_generate_short_metadata", {"index": 0})["ok"] in {True, False}
    assert call(server, "videoflow_analyze_short", {"index": 0})["ok"] in {True, False}
    assert call(
        server, "videoflow_analyze_short_llm", {"index": 0, "base_url": "http://127.0.0.1:9/v1"}
    )["ok"] in {True, False}

    recipe = {
        "schema_version": 1,
        "id": "mcp_demo",
        "name": "MCP demo",
        "steps": [{"id": "ingest", "type": "ingest", "params": {}}],
    }
    assert (
        call(
            server,
            "videoflow_run_recipe_inline",
            {"recipe": recipe, "source": str(source), "output": str(tmp_path / "inline")},
        )["ok"]
        is True
    )
    assert (
        call(
            server,
            "videoflow_run_step",
            {
                "step_id": "ingest",
                "recipe": recipe,
                "source": str(source),
                "output": str(tmp_path / "step"),
            },
        )["ok"]
        is True
    )
    assert (
        call(
            server,
            "videoflow_run_batch",
            {"recipe": recipe, "source_dir": str(tmp_path), "output_root": str(tmp_path / "batch")},
        )["ok"]
        is True
    )


def test_mcp_short_media_and_copilot_tools(monkeypatch, tmp_path: Path) -> None:
    _client_obj, manager, server, job, source = _setup(monkeypatch, tmp_path)
    job_id = str(job.job_id)

    from videoflow.application import short_metadata as short_metadata_module

    monkeypatch.setattr(
        short_metadata_module,
        "generate_short_metadata",
        lambda **kwargs: {"title": "T", "description": "D", "hashtags": ["#a"]},
    )
    monkeypatch.setattr(
        server_module,
        "enqueue_publish",
        lambda **kwargs: {"id": "item-1", "target": kwargs.get("target_name")},
    )
    assert call(server, "videoflow_schedule_short", {"index": 0, "target": "demo"})["ok"] is True

    monkeypatch.setattr(server_module, "edit_short_service", lambda **kwargs: {"title": "Edited"})
    assert call(server, "videoflow_edit_short", {"index": 0, "title": "Edited"})["ok"] is True

    monkeypatch.setattr(
        server_module,
        "apply_llm_emoji",
        lambda **kwargs: {"emoji_map": {"hello": "👋"}, "short": {"title": "Hook"}},
    )
    assert call(server, "videoflow_generate_short_emoji", {"index": 0})["ok"] is True

    monkeypatch.setattr(
        server_module,
        "generate_short_thumbnail",
        lambda **kwargs: {"path": str(tmp_path / "thumb.png")},
    )
    assert call(server, "videoflow_generate_short_thumbnail", {"index": 0})["ok"] is True

    monkeypatch.setattr(
        server_module,
        "generate_short_voiceover",
        lambda **kwargs: {"path": str(tmp_path / "voice.mp3")},
    )
    assert (
        call(server, "videoflow_generate_short_voiceover", {"index": 0, "text": "hello"})["ok"]
        is True
    )

    monkeypatch.setattr(
        server_module,
        "generate_short_dubbing",
        lambda **kwargs: {"path": str(tmp_path / "dub.mp3")},
    )
    assert call(server, "videoflow_dub_short", {"index": 0, "target_language": "en"})["ok"] is True

    monkeypatch.setattr(server_module, "analyze_short_entry", lambda **kwargs: {"score": 1})
    assert call(server, "videoflow_analyze_short", {"index": 0})["ok"] is True
    monkeypatch.setattr(server_module, "analyze_short_llm_entry", lambda **kwargs: {"score": 2})
    assert (
        call(
            server, "videoflow_analyze_short_llm", {"index": 0, "base_url": "http://127.0.0.1:9/v1"}
        )["ok"]
        is True
    )

    from videoflow.core.recipe import parse_recipe

    recipe = parse_recipe(
        {
            "schema_version": 1,
            "id": "copilot_demo",
            "name": "Copilot",
            "steps": [{"id": "ingest", "type": "ingest", "params": {}}],
        }
    )
    monkeypatch.setattr(server_module, "build_llm", lambda: None)
    monkeypatch.setattr(server_module, "propose_recipe", lambda client, prompt: recipe)
    assert call(server, "videoflow_copilot_recipe", {"prompt": "ingest"})["ok"] is True
    monkeypatch.setattr(
        server_module,
        "propose_timeline_edits",
        lambda client, prompt, clips: [
            {"clip_id": "v1", "action": "trim", "start_sec": 0.0, "end_sec": 1.0}
        ],
    )
    assert (
        call(
            server,
            "videoflow_copilot_timeline",
            {"prompt": "shorten", "apply": True, "job_id": job_id},
        )["ok"]
        is True
    )

    export = call(
        server, "videoflow_export_fcpxml", {"output_path": str(tmp_path / "export.fcpxml")}
    )
    assert export["ok"] is True, export

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    audio = upload_dir / "a.mp3"
    audio.write_bytes(b"audio")
    image = upload_dir / "a.png"
    image.write_bytes(b"png")
    font = upload_dir / "a.ttf"
    font.write_bytes(b"font")
    monkeypatch.setattr(server_module, "save_music", lambda name, body: {"name": name})
    monkeypatch.setattr(server_module, "save_image", lambda name, body: {"name": name})
    monkeypatch.setattr(server_module, "save_font", lambda name, body: {"name": name})
    assert call(server, "videoflow_upload_music", {"file_path": str(audio)})["ok"] is True
    assert call(server, "videoflow_upload_image", {"file_path": str(image)})["ok"] is True
    assert call(server, "videoflow_upload_font", {"file_path": str(font)})["ok"] is True

    monkeypatch.setattr(
        server_module, "install_model", lambda model_id, allow_network: {"id": model_id}
    )
    monkeypatch.setattr(server_module, "remove_model", lambda model_id: None)
    assert call(server, "videoflow_install_model", {"model_id": "demo"})["ok"] is True
    assert call(server, "videoflow_remove_model", {"model_id": "demo"})["ok"] is True

    for index, args in enumerate(
        [
            {"min_duration": 0},
            {"aspect_ratio": "4:3"},
            {"prompt_mode": "bad"},
            {"hook_mode": "bad"},
            {"reframe_mode": "bad"},
            {"start_sec": 10, "end_sec": 1},
            {"count": 0},
            {"count": 1, "min_count": 2},
            {"selection_mode": "bad"},
        ]
    ):
        assert call(server, "videoflow_generate_shorts", args)["ok"] is False, index
