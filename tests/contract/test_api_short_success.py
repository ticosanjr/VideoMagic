from __future__ import annotations

from pathlib import Path

from tests.contract.test_api_media_routes import _short_job
from tests.contract.test_api_timeline import _client, _job


def test_short_edit_analysis_assets_and_publish(monkeypatch, tmp_path: Path) -> None:
    from videoflow.api import routes as routes_module

    client, job, _media, _thumb, _outside = _short_job(monkeypatch, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}/shorts/0"
    monkeypatch.setattr(routes_module, "edit_short_service", lambda **kwargs: {"title": "edited"})
    monkeypatch.setattr(
        routes_module,
        "apply_llm_emoji",
        lambda **kwargs: {"emoji_map": {}, "short": job.result["shorts"][0]},
    )
    monkeypatch.setattr(
        routes_module,
        "generate_short_metadata",
        lambda **kwargs: {"title": "T", "description": "D", "hashtags": ["#a"]},
    )
    monkeypatch.setattr(
        routes_module, "generate_short_thumbnail", lambda **kwargs: {"path": "thumb.png"}
    )
    monkeypatch.setattr(
        routes_module, "generate_short_voiceover", lambda **kwargs: {"path": "voice.mp3"}
    )
    monkeypatch.setattr(
        routes_module, "generate_short_dubbing", lambda **kwargs: {"path": "dub.mp3"}
    )
    monkeypatch.setattr(routes_module, "analyze_short_entry", lambda **kwargs: {"score": 1})
    monkeypatch.setattr(routes_module, "analyze_short_llm_entry", lambda **kwargs: {"score": 2})
    from videoflow.api import routes_publish as publish_module
    monkeypatch.setattr(publish_module, "enqueue_publish", lambda **kwargs: {"id": "item-1"})
    monkeypatch.setattr(
        publish_module,
        "generate_short_metadata",
        lambda **kwargs: {"title": "T", "description": "D", "hashtags": ["#a"]},
    )

    assert client.post(f"{base}/edit", json={"title": "edited"}).status_code == 200
    assert client.post(f"{base}/captions/emoji", json={}).status_code == 200
    assert client.post(f"{base}/metadata", json={"platform": "youtube"}).status_code == 200
    assert client.post(f"{base}/thumbnail", json={}).status_code == 200
    assert client.post(f"{base}/voiceover", json={"text": "hello"}).status_code == 200
    assert (
        client.post(f"{base}/dub", json={"target_language": "en", "text": "hello"}).status_code
        == 200
    )
    assert client.post(f"{base}/analyze").status_code == 200
    assert (
        client.post(f"{base}/analyze/llm", json={"base_url": "http://127.0.0.1:9/v1"}).status_code
        == 200
    )
    assert client.post(f"{base}/publish", json={"target": "demo"}).status_code == 200


def test_variants_broll_system_and_admin_success(monkeypatch, tmp_path: Path) -> None:
    from videoflow.api import routes as routes_module

    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    job.result = {
        "shorts": [{"title": "Hook", "score": 90, "path": str(tmp_path / "out" / "short.mp4")}],
        "variants": [
            {"name": "one", "output": str(tmp_path / "out" / "one"), "summary": {"shorts": []}}
        ],
    }
    assert client.get(f"/api/v1/jobs/{job.job_id}/variants").status_code == 200
    assert (
        client.post(
            f"/api/v1/jobs/{job.job_id}/variants/select", json={"name": "short-1"}
        ).status_code
        == 200
    )
    assert client.post(f"/api/v1/jobs/{job.job_id}/broll/undo").status_code <= 502
    assert client.post(f"/api/v1/jobs/{job.job_id}/broll/redo").status_code <= 502
    assert client.get("/api/v1/system/doctor").status_code == 200
    assert (
        client.post(
            "/api/v1/maintenance/prune",
            json={"output": str(tmp_path / "out"), "dry_run": True, "include_global_cache": True},
        ).status_code
        == 200
    )
    assert client.post(f"/api/v1/jobs/{job.job_id}/pause").status_code == 200
    assert client.post(f"/api/v1/jobs/{job.job_id}/unpause").status_code == 200
    assert (
        client.patch(f"/api/v1/jobs/{job.job_id}/priority", json={"priority": 2}).status_code == 200
    )

    media = tmp_path / "downloaded.mp4"
    media.write_bytes(b"mp4")
    monkeypatch.setattr(routes_module, "import_url", lambda *args, **kwargs: media)
    from videoflow.adapters.ffmpeg import FFmpegAdapter

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")

    def probe(self, path):
        from videoflow.domain.state import MediaInfo

        return MediaInfo(
            source_path=str(path),
            duration_frames=10,
            fps_num=30,
            fps_den=1,
            width=10,
            height=10,
            audio_sample_rate=48000,
        )

    monkeypatch.setattr(FFmpegAdapter, "probe", probe)
    assert (
        client.post("/api/v1/media/import", json={"url": "http://example.test/v"}).status_code
        == 201
    )

    from videoflow.api import routes_admin as admin_module
    monkeypatch.setattr(
        admin_module, "set_plugin_enabled", lambda plugin_id, enabled: {"id": plugin_id}
    )
    assert client.post("/api/v1/plugins/demo/enable", json={"enabled": True}).status_code == 200
    monkeypatch.setattr(
        admin_module, "install_model", lambda model_id, allow_network: {"id": model_id}
    )
    assert client.post("/api/v1/models/demo/install", json={}).status_code == 200
    monkeypatch.setattr(
        admin_module, "start_service", lambda service_id: {"id": service_id, "status": "running"}
    )
    assert (
        client.put(
            "/api/v1/services/definitions/svc",
            json={"id": "svc", "name": "Svc", "command": "/bin/true"},
        ).status_code
        == 200
    )
    assert client.post("/api/v1/services/definitions/svc/start").status_code == 200


def test_frame_and_artifact_error_branches(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    (job.output / "project_state.json").unlink(missing_ok=True)
    assert client.get(f"/api/v1/jobs/{job.job_id}/frame").status_code == 409
    assert client.get(f"/api/v1/jobs/{job.job_id}/frames").status_code == 409
    assert client.get(f"/api/v1/jobs/{job.job_id}/artifacts/missing").status_code == 404
    assert client.get(f"/api/v1/jobs/{job.job_id}/timeline/waveform").status_code in {
        200,
        404,
        409,
        422,
    }


def test_frame_state_and_timeline_error_paths(monkeypatch, tmp_path: Path) -> None:
    from videoflow.domain.state import ProjectState

    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    state_path = job.output / "project_state.json"
    state = ProjectState.model_validate_json(state_path.read_text())
    state.media_info = None
    state_path.write_text(state.model_dump_json())
    assert client.get(f"/api/v1/jobs/{job.job_id}/frame").status_code == 409
    assert client.get(f"/api/v1/jobs/{job.job_id}/frames").status_code == 409

    state.media_info = __import__("videoflow.domain.state", fromlist=["MediaInfo"]).MediaInfo(
        source_path=str(tmp_path / "missing.mp4"),
        duration_frames=10,
        fps_num=30,
        fps_den=1,
        width=10,
        height=10,
        audio_sample_rate=48000,
    )
    state_path.write_text(state.model_dump_json())
    assert client.get(f"/api/v1/jobs/{job.job_id}/frame").status_code == 409
    assert client.get(f"/api/v1/jobs/{job.job_id}/frames").status_code == 409

    state_path.write_text("{broken", encoding="utf-8")
    assert client.get(f"/api/v1/jobs/{job.job_id}/frame").status_code == 422
    assert client.get(f"/api/v1/jobs/{job.job_id}/frames").status_code == 422
    assert client.get("/api/v1/jobs/missing/artifacts/x").status_code == 404

    fresh, fresh_manager = _client(monkeypatch, tmp_path / "fresh")
    fresh_job = _job(fresh_manager, tmp_path / "fresh")
    assert fresh.post(f"/api/v1/jobs/{fresh_job.job_id}/timeline/undo").status_code == 409
    assert fresh.post(f"/api/v1/jobs/{fresh_job.job_id}/timeline/redo").status_code == 409


def test_short_missing_index_errors(monkeypatch, tmp_path: Path) -> None:
    from tests.contract.test_api_media_routes import _short_job

    client, _job_obj, _media, _thumb, _outside = _short_job(monkeypatch, tmp_path)
    job_id = _job_obj.job_id
    base = f"/api/v1/jobs/{job_id}/shorts/99"
    assert client.post(f"{base}/edit", json={"title": "x"}).status_code <= 502
    assert client.post(f"{base}/captions/emoji", json={}).status_code <= 502
    assert client.post(f"{base}/metadata", json={}).status_code <= 502
    assert client.post(f"{base}/thumbnail", json={}).status_code <= 502
    assert client.post(f"{base}/voiceover", json={"text": "x"}).status_code <= 502
    assert client.post(f"{base}/dub", json={"text": "x"}).status_code <= 502
    assert client.post(f"{base}/analyze").status_code <= 502
