from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx

from tests.contract.test_api_timeline import _client, _job


def _error(response) -> dict:
    payload = response.json()
    detail = payload.get("detail", payload)
    if isinstance(detail, dict):
        return detail
    return {"errors": detail}


def _recipe(recipe_id: str = "coverage_recipe") -> dict:
    return {
        "schema_version": 1,
        "id": recipe_id,
        "name": "Coverage",
        "steps": [{"id": "ingest", "type": "ingest", "params": {}}],
    }


def test_request_model_validators_and_bad_json(monkeypatch, tmp_path: Path) -> None:
    client, _manager = _client(monkeypatch, tmp_path)
    base = {"source": str(tmp_path / "source.mp4"), "output": str(tmp_path / "out")}
    cases = [
        (
            {**base, "zoom_min_scale": 2.0, "zoom_max_scale": 1.5},
            "zoom_min_scale exceeds zoom_max_scale",
        ),
        (
            {**base, "zoom_min_scale": 1.0, "zoom_max_scale": 2.0, "punch_in_scale": 2.5},
            "punch_in_scale must be inside the zoom window",
        ),
        (
            {**base, "shorts_count": 2, "shorts_min_count": 3},
            "shorts_min_count exceeds shorts_count",
        ),
        (
            {**base, "shorts_source_start_sec": 10.0, "shorts_source_end_sec": 5.0},
            "shorts_source_end_sec must be greater than shorts_source_start_sec",
        ),
    ]
    for payload, message in cases:
        response = client.post("/api/v1/jobs", json=payload)
        assert response.status_code == 422, response.text
        assert message in response.text

    no_recipe = client.post("/api/v1/recipes/run", json={"source": "s", "output": "o"})
    assert no_recipe.status_code == 422
    assert "provide exactly one of recipe or recipe_id" in no_recipe.text

    both = client.post(
        "/api/v1/recipes/run",
        json={"recipe": _recipe(), "recipe_id": "coverage_recipe"},
    )
    assert both.status_code == 422
    assert "provide exactly one of recipe or recipe_id" in both.text

    batch = client.post(
        "/api/v1/batches",
        json={"source_dir": str(tmp_path), "output_root": str(tmp_path / "batch")},
    )
    assert batch.status_code == 422
    assert "provide exactly one of recipe or recipe_id" in batch.text

    trim = client.post(
        "/api/v1/jobs/missing/shorts/0/edit",
        json={"start_sec": 5.0, "end_sec": 2.0},
    )
    assert trim.status_code == 422
    assert "end_sec must be greater than start_sec" in trim.text

    malformed = client.post(
        "/api/v1/jobs",
        content=b"{not json",
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == 422


def test_asset_filesystem_and_media_error_paths(monkeypatch, tmp_path: Path) -> None:
    from videoflow.api import routes as routes_module
    from videoflow.domain.errors import FilesystemError
    from videoflow.domain.state import MediaInfo

    client, _manager = _client(monkeypatch, tmp_path)

    def fail_save(name, body):
        raise FilesystemError("bad asset bytes")

    savers = {
        "music": ("save_music", "music_invalid"),
        "sfx": ("save_sfx", "sfx_invalid"),
        "images": ("save_image", "image_invalid"),
        "fonts": ("save_font", "font_invalid"),
    }
    for kind, (attribute, code) in savers.items():
        monkeypatch.setattr(routes_module, attribute, fail_save)
        response = client.post(f"/api/v1/assets/{kind}?name=bad.bin", content=b"x")
        assert response.status_code == 422, response.text
        assert _error(response)["code"] == code

    music = client.delete("/api/v1/assets/music/missing.mp3")
    assert music.status_code in {404, 500}
    assert _error(music)["code"] in {"asset_not_found", "filesystem_error"}
    sfx = client.delete("/api/v1/assets/sfx/missing.wav")
    assert sfx.status_code == 404
    assert _error(sfx)["code"] == "asset_not_found"
    images = client.delete("/api/v1/assets/images/missing.png")
    assert images.status_code in {404, 500}
    fonts = client.delete("/api/v1/assets/fonts/missing.ttf")
    assert fonts.status_code in {404, 500}

    monkeypatch.setattr(routes_module, "get_asset", lambda asset_id: None)
    assert client.get("/api/v1/assets/missing/file").status_code == 404

    outside = tmp_path.parent / "outside.bin"
    outside.write_bytes(b"x")
    monkeypatch.setattr(
        routes_module, "get_asset", lambda asset_id: {"id": asset_id, "path": str(outside)}
    )
    denied = client.get("/api/v1/assets/outside/file")
    assert denied.status_code == 403
    assert _error(denied)["code"] == "path_not_allowed"

    monkeypatch.setattr(
        routes_module,
        "get_asset",
        lambda asset_id: {"id": asset_id, "path": str(tmp_path / "gone.bin")},
    )
    gone = client.get("/api/v1/assets/gone/file")
    assert gone.status_code == 404
    assert _error(gone)["code"] == "asset_file_not_found"

    missing_asset = client.patch("/api/v1/assets/missing", json={"tags": ["a"]})
    assert missing_asset.status_code == 404
    assert _error(missing_asset)["code"] == "asset_not_found"
    removed = client.delete("/api/v1/assets/missing")
    assert removed.status_code == 404
    assert _error(removed)["code"] == "asset_not_found"

    scan = client.post("/api/v1/assets/scan", json={"directory": "/definitely/not/allowed"})
    assert scan.status_code == 403

    assert client.get("/api/v1/fs/roots").status_code == 200
    jailed = client.get("/api/v1/fs/list", params={"path": "/definitely/not/allowed"})
    assert jailed.status_code == 403
    assert _error(jailed)["code"] == "path_not_allowed"

    def explode(*args, **kwargs):
        raise OverflowError("too many entries")

    monkeypatch.setattr(routes_module, "list_directory", explode)
    listing = client.get("/api/v1/fs/list")
    assert listing.status_code == 500
    assert _error(listing)["code"] == "filesystem_error"

    missing_parent = client.post(
        "/api/v1/fs/mkdir", json={"parent": str(tmp_path / "gone"), "name": "new"}
    )
    assert missing_parent.status_code == 404
    assert _error(missing_parent)["code"] == "path_not_found"
    existing = tmp_path / "already"
    existing.mkdir()
    collision = client.post(
        "/api/v1/fs/mkdir", json={"parent": str(tmp_path), "name": "already"}
    )
    assert collision.status_code == 409
    assert _error(collision)["code"] == "directory_exists"
    invalid = client.post(
        "/api/v1/fs/mkdir", json={"parent": str(tmp_path), "name": "../escape"}
    )
    assert invalid.status_code == 422
    assert _error(invalid)["code"] == "invalid_directory_name"

    assert client.get("/api/v1/media/probe", params={"path": "/nope.mp4"}).status_code == 403
    missing_media = client.get(
        "/api/v1/media/probe", params={"path": str(tmp_path / "missing.mp4")}
    )
    assert missing_media.status_code == 422
    assert _error(missing_media)["code"] == "media_not_found"

    present = tmp_path / "present.mp4"
    present.write_bytes(b"fake")

    def fake_probe(self, path):
        return MediaInfo(
            source_path=str(path),
            duration_frames=42,
            fps_num=30,
            fps_den=1,
            width=16,
            height=16,
            audio_sample_rate=48000,
        )

    monkeypatch.setattr(routes_module.FFmpegAdapter, "probe", fake_probe)
    probed = client.get("/api/v1/media/probe", params={"path": str(present)})
    assert probed.status_code == 200
    assert probed.json()["media"]["duration_frames"] == 42
    assert probed.json()["size_bytes"] == 4

    def fail_import(*args, **kwargs):
        from videoflow.domain.errors import IngestError

        raise IngestError("cannot import")

    monkeypatch.setattr(routes_module, "import_url", fail_import)
    imported = client.post("/api/v1/media/import", json={"url": "http://example.test/v"})
    assert imported.status_code == 422
    assert _error(imported)["code"] == "ingest_failed"


def test_provider_secret_voice_clone_and_plugin_errors(monkeypatch, tmp_path: Path) -> None:
    from videoflow.api import routes as routes_module

    client, _manager = _client(monkeypatch, tmp_path)

    def fail_get(*args, **kwargs):
        raise httpx.ConnectError("provider down")

    monkeypatch.setattr(routes_module.httpx, "get", fail_get)
    probe = client.post(
        "/api/v1/providers/test", json={"base_url": "http://127.0.0.1:9/v1"}
    )
    assert probe.status_code == 200
    assert probe.json()["ok"] is False
    assert probe.json()["status_code"] is None
    assert "provider down" in probe.json()["message"]

    empty = client.post("/api/v1/providers/demo/secret", json={})
    assert empty.status_code == 422
    assert _error(empty)["code"] == "empty_secret"
    unknown_secret = client.post(
        "/api/v1/providers/missing/secret", json={"value": "x"}
    )
    assert unknown_secret.status_code == 404
    assert _error(unknown_secret)["code"] == "provider_not_found"
    unknown_delete = client.delete("/api/v1/providers/missing/secret")
    assert unknown_delete.status_code == 404
    assert _error(unknown_delete)["code"] == "provider_not_found"

    provider = {
        "id": "plain",
        "name": "Plain",
        "capability": "llm",
        "base_url": "http://127.0.0.1:9/v1",
        "model": "plain",
    }
    assert client.put("/api/v1/providers/plain", json=provider).status_code == 200
    no_name = client.post("/api/v1/providers/plain/secret", json={"value": "x"})
    assert no_name.status_code == 422
    assert _error(no_name)["code"] == "secret_name_missing"
    assert client.delete("/api/v1/providers/plain/secret").status_code == 200

    missing_provider = client.delete("/api/v1/providers/missing")
    assert missing_provider.status_code == 409
    assert _error(missing_provider)["code"] == "state_not_ready"
    missing_default = client.post("/api/v1/providers/missing/default")
    assert missing_default.status_code == 409
    assert _error(missing_default)["code"] == "state_not_ready"
    unknown_capability = client.get(
        "/api/v1/providers/resolve", params={"capability": "telepathy"}
    )
    assert unknown_capability.status_code == 422
    assert _error(unknown_capability)["code"] == "unknown_capability"
    assert client.get("/api/v1/providers").status_code == 200

    created = client.post(
        "/api/v1/voice-clone/profiles",
        json={"name": "Voice", "consent_ref": "signed-consent"},
    )
    assert created.status_code == 201, created.text
    profile_id = created.json()["profile"]["id"]
    no_consent = client.post(
        "/api/v1/voice-clone/profiles", json={"name": "Voice", "consent_ref": "   "}
    )
    assert no_consent.status_code == 409
    assert _error(no_consent)["code"] == "state_not_ready"
    missing_profile = client.delete("/api/v1/voice-clone/profiles/missing")
    assert missing_profile.status_code == 409
    missing_synth = client.post(
        "/api/v1/voice-clone/synthesize",
        json={"profile_id": "missing", "text": "hello"},
    )
    assert missing_synth.status_code == 409
    assert _error(missing_synth)["code"] == "state_not_ready"
    unsupported = client.post(
        "/api/v1/voice-clone/synthesize",
        json={"profile_id": profile_id, "text": "hello"},
    )
    assert unsupported.status_code == 501
    assert _error(unsupported)["code"] == "not_implemented"
    assert _error(unsupported)["capability"] == "voice_clone"
    status = client.get("/api/v1/voice-clone/status")
    assert status.status_code == 200
    assert status.json()["available"] is False
    profiles = client.get("/api/v1/voice-clone/profiles")
    assert [item["id"] for item in profiles.json()["profiles"]] == [profile_id]
    assert client.delete(f"/api/v1/voice-clone/profiles/{profile_id}").status_code == 200

    unknown_plugin = client.post(
        "/api/v1/plugins/missing/enable", json={"enabled": True}
    )
    assert unknown_plugin.status_code == 404
    assert _error(unknown_plugin)["code"] == "plugin_not_found"
    plugins = client.get("/api/v1/plugins")
    assert plugins.status_code == 200
    assert "panels" in plugins.json()
    assert client.post("/api/v1/plugins/reload").status_code == 200


def test_project_settings_template_and_config_errors(monkeypatch, tmp_path: Path) -> None:
    client, _manager = _client(monkeypatch, tmp_path)

    created = client.post(
        "/api/v1/projects",
        json={"name": "Project", "source": str(tmp_path / "s.mp4"), "output": str(tmp_path)},
    )
    assert created.status_code == 201
    project_id = created.json()["project"]["id"]
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 200
    updated = client.patch(f"/api/v1/projects/{project_id}", json={"name": "Renamed"})
    assert updated.status_code == 200
    assert updated.json()["project"]["name"] == "Renamed"
    missing_get = client.get("/api/v1/projects/missing")
    assert missing_get.status_code == 409
    assert _error(missing_get)["code"] == "state_not_ready"
    assert client.patch("/api/v1/projects/missing", json={"name": "x"}).status_code == 409
    assert client.delete("/api/v1/projects/missing").status_code == 409
    assert client.delete(f"/api/v1/projects/{project_id}").status_code == 200

    settings = client.get("/api/v1/settings")
    assert settings.status_code == 200
    payload = settings.json()["settings"]
    assert client.put("/api/v1/settings", json=payload).status_code == 200
    assert client.post("/api/v1/settings/import", json=payload).status_code == 200
    reset = client.post("/api/v1/settings/reset")
    assert reset.status_code == 200
    exported = client.get("/api/v1/settings/export")
    assert exported.status_code == 200
    assert exported.json()["file"] == "videoflow-settings.json"

    missing_project = client.get("/api/v1/project-templates/missing")
    assert missing_project.status_code == 409
    assert client.post("/api/v1/project-templates/missing/apply").status_code == 409
    assert client.delete("/api/v1/project-templates/missing").status_code == 409

    missing_brand = client.get("/api/v1/brand-templates/missing")
    assert missing_brand.status_code == 409
    assert client.post("/api/v1/brand-templates/missing/apply").status_code == 409
    assert client.delete("/api/v1/brand-templates/missing").status_code == 409

    bad_config = client.post(
        "/api/v1/config/import", json={"schema_version": 99, "options": {}}
    )
    assert bad_config.status_code in {422, 500}
    assert _error(bad_config)["code"] == "invalid_config"

    bad_project_name = client.put(
        "/api/v1/project-templates/!!!", json={"name": "x", "options": {}}
    )
    assert bad_project_name.status_code == 500
    assert _error(bad_project_name)["code"] == "filesystem_error"
    bad_brand_name = client.put("/api/v1/brand-templates/!!!", json={"name": "x"})
    assert bad_brand_name.status_code == 500
    assert _error(bad_brand_name)["code"] == "filesystem_error"


def test_recipe_wiring_errors_and_save(monkeypatch, tmp_path: Path) -> None:
    from pydantic import ValidationError

    from videoflow.api import routes as routes_module

    client, _manager = _client(monkeypatch, tmp_path)
    source = str(tmp_path / "source.mp4")
    output = str(tmp_path / "recipe-out")

    missing_dry = client.post("/api/v1/recipes/dry-run", json={"recipe_id": "missing"})
    assert missing_dry.status_code == 422
    assert _error(missing_dry)["code"] == "recipe_invalid"
    missing_run = client.post("/api/v1/recipes/run", json={"recipe_id": "missing"})
    assert missing_run.status_code == 422
    assert _error(missing_run)["code"] == "recipe_invalid"
    missing_detail = client.get("/api/v1/recipes/missing")
    assert missing_detail.status_code == 422
    assert _error(missing_detail)["code"] == "recipe_invalid"

    wrong_step = client.post(
        "/api/v1/steps/not_a_step/run",
        json={"recipe": _recipe(), "source": source, "output": output},
    )
    assert wrong_step.status_code == 422
    assert "Unknown or disabled step: not_a_step" in wrong_step.text

    mismatch = client.put(
        "/api/v1/recipes/url_id",
        json={**_recipe("body_id"), "name": "Mismatch"},
    )
    assert mismatch.status_code == 422
    assert "recipe id does not match the URL" in mismatch.text

    saved = client.post(
        "/api/v1/recipes/run",
        json={
            "recipe": _recipe("saved_by_run"),
            "source": source,
            "output": output,
            "save_recipe": True,
        },
    )
    assert saved.status_code == 202, saved.text
    assert client.get("/api/v1/recipes/saved_by_run").status_code == 200

    bad = client.post(
        "/api/v1/batches",
        json={"source_dir": str(tmp_path), "output_root": output, "recipe_id": "missing"},
    )
    assert bad.status_code == 422
    assert _error(bad)["code"] == "recipe_invalid"

    class FakeStep:
        @staticmethod
        def validate_params(params):
            raise ValidationError.from_exception_data(
                "Step",
                [
                    {
                        "type": "value_error",
                        "loc": (),
                        "input": params,
                        "ctx": {"error": ValueError("bad params")},
                    }
                ],
            )

    monkeypatch.setattr(routes_module, "get_step", lambda step_id: FakeStep())
    invalid_params = client.post("/api/v1/recipes/validate", json=_recipe("params_bad"))
    assert invalid_params.status_code == 422
    assert "params_bad" not in invalid_params.text
    assert "ingest:" in invalid_params.text


def test_publish_short_states_and_template_job_options(monkeypatch, tmp_path: Path) -> None:
    from tests.contract.test_api_media_routes import _short_job

    client, job, _media, _thumb, _outside = _short_job(monkeypatch, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}/shorts"

    out_of_range = client.post(f"{base}/9/publish", json={"target": "demo"})
    assert out_of_range.status_code == 409
    assert "out of range" in _error(out_of_range)["message"]
    missing_path = client.post(f"{base}/1/publish", json={"target": "demo"})
    assert missing_path.status_code == 409
    assert "asset is missing" in _error(missing_path)["message"]

    project = {"name": "opts", "description": "", "options": {"crf": 20}}
    assert client.put("/api/v1/project-templates/opts", json=project).status_code == 200
    brand = {"name": "brand", "description": ""}
    assert client.put("/api/v1/brand-templates/brand", json=brand).status_code == 200

    body = {
        "source": str(tmp_path / "source.mp4"),
        "output": str(tmp_path / "templated"),
        "project_template": "opts",
        "brand_template": "brand",
    }
    wired = client.post("/api/v1/jobs", json=body)
    assert wired.status_code == 202, wired.text

    unknown_project = client.post(
        "/api/v1/jobs", json={**body, "project_template": "missing", "output": str(tmp_path / "x1")}
    )
    assert unknown_project.status_code == 409
    assert _error(unknown_project)["code"] == "state_not_ready"
    unknown_brand = client.post(
        "/api/v1/jobs", json={**body, "brand_template": "missing", "output": str(tmp_path / "x2")}
    )
    assert unknown_brand.status_code == 409
    assert _error(unknown_brand)["code"] == "state_not_ready"


def test_job_state_guards_for_pending_work(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}"
    original_result = job.result
    job.status = "running"
    job.result = None
    pending = [
        ("POST", f"{base}/shorts/0/publish", {"target": "demo"}),
        ("POST", f"{base}/shorts/0/edit", {"title": "x"}),
        ("POST", f"{base}/shorts/0/captions/emoji", {}),
        ("POST", f"{base}/shorts/0/metadata", {}),
        ("POST", f"{base}/shorts/0/thumbnail", {}),
        ("POST", f"{base}/shorts/0/voiceover", {"text": "hello"}),
        ("POST", f"{base}/shorts/0/dub", {"text": "hello"}),
        ("POST", f"{base}/shorts/0/analyze", None),
        ("POST", f"{base}/shorts/0/analyze/llm", {}),
        ("POST", f"{base}/preview", None),
        ("POST", f"{base}/render", None),
        ("POST", f"{base}/retry", None),
        ("POST", f"{base}/resume", {"approved": True}),
    ]
    for method, path, body in pending:
        response = client.request(method, path, json=body)
        assert response.status_code == 409, path
        assert _error(response)["code"] == "state_not_ready", path
    job.status = "succeeded"
    job.result = original_result
    assert client.get(base).json()["job"]["status"] == "succeeded"


def test_missing_job_ids_for_mutation_routes(monkeypatch, tmp_path: Path) -> None:
    client, _manager = _client(monkeypatch, tmp_path)
    base = "/api/v1/jobs/missing"
    calls = [
        ("POST", f"{base}/pause", None),
        ("POST", f"{base}/unpause", None),
        ("PATCH", f"{base}/priority", {"priority": 1}),
        ("POST", f"{base}/retry", None),
        ("POST", f"{base}/resume", {"approved": True}),
        ("GET", f"{base}/events", None),
        ("GET", f"{base}/variants", None),
        ("POST", f"{base}/variants/select", {"name": "one"}),
        ("GET", f"{base}/dag", None),
        ("GET", f"{base}/logs", None),
        ("PATCH", f"{base}/timeline", {"clip_id": "v1", "action": "move"}),
        ("PATCH", f"{base}/timeline/clip/v1", {"scale": 1.1}),
        (
            "PATCH",
            f"{base}/timeline/batch",
            {"edits": [{"clip_id": "v1", "action": "move", "delta_sec": 0.1}]},
        ),
        ("POST", f"{base}/timeline/undo", None),
        ("POST", f"{base}/timeline/redo", None),
        ("PATCH", f"{base}/captions/0", {"text": "x"}),
        ("GET", f"{base}/review", None),
        ("PATCH", f"{base}/review", {"approved": True}),
        ("GET", f"{base}/review/comments", None),
        ("POST", f"{base}/review/comments", {"text": "x"}),
        ("GET", f"{base}/thumbnails", None),
        ("GET", f"{base}/clips/v1/thumbnail", None),
        ("GET", f"{base}/thumbnails/metrics", None),
        ("POST", f"{base}/thumbnails/a.png/metric", {"impressions": 1}),
        ("POST", f"{base}/thumbnails/select", {"name": "a.png"}),
        ("POST", f"{base}/broll/undo", None),
        ("POST", f"{base}/broll/redo", None),
        ("GET", f"{base}/broll", None),
        ("PATCH", f"{base}/broll", {"title": "x", "approved": [], "order": []}),
        ("GET", f"{base}/timeline/meta", None),
        ("PUT", f"{base}/timeline/meta", {"markers": [], "tracks": {}, "comments": []}),
        ("POST", f"{base}/timeline/markers", {"time_sec": 1.0}),
        ("DELETE", f"{base}/timeline/markers/m1", None),
        (
            "POST",
            f"{base}/timeline/overlays",
            {"path": "/tmp/overlay.png", "start_sec": 0.0, "duration_sec": 1.0},
        ),
        ("DELETE", f"{base}/timeline/overlays/o1", None),
        ("GET", f"{base}/timeline/comments", None),
        ("POST", f"{base}/timeline/comments", {"clip_id": "v1", "text": "x"}),
        ("DELETE", f"{base}/timeline/comments/c1", None),
        ("PUT", f"{base}/timeline/tracks/video", {"muted": False, "locked": False, "solo": False}),
        ("GET", f"{base}/timeline", None),
        ("GET", f"{base}/timeline/waveform", None),
        ("POST", f"{base}/preview", None),
        ("POST", f"{base}/render", None),
        ("GET", f"{base}/preview/status", None),
        ("GET", f"{base}/preview/file", None),
        ("GET", f"{base}/render/status", None),
        ("GET", f"{base}/render/file", None),
        ("GET", f"{base}/frames", None),
        ("GET", f"{base}/frame", None),
        ("GET", f"{base}/artifacts/x", None),
        ("GET", f"{base}/shorts/0", None),
        ("GET", f"{base}/shorts/0/file", None),
        ("GET", f"{base}/shorts/0/thumbnail", None),
        ("POST", f"{base}/shorts/0/edit", {"title": "x"}),
        ("POST", f"{base}/shorts/0/analyze", None),
        ("GET", f"{base}/state", None),
        ("GET", f"{base}/assistant/history", None),
        ("POST", f"{base}/assistant", {"prompt": "hi"}),
        ("POST", f"{base}/assistant/approve", {"approval_id": "a1"}),
        ("POST", f"{base}/copilot/timeline", {"prompt": "move"}),
    ]
    for method, path, body in calls:
        response = client.request(method, path, json=body)
        assert response.status_code == 404, path
        assert _error(response)["code"] == "job_not_found", path

    cancel_render = client.post(f"{base}/render/cancel")
    assert cancel_render.status_code == 404
    assert _error(cancel_render)["code"] == "render_not_found"
    cancel_preview = client.post(f"{base}/preview/cancel")
    assert cancel_preview.status_code == 404
    assert _error(cancel_preview)["code"] == "preview_not_found"

    for method, path in [
        ("GET", "/api/v1/batches/missing"),
        ("POST", "/api/v1/batches/missing/resume"),
        ("POST", "/api/v1/batches/missing/cancel"),
    ]:
        response = client.request(method, path)
        assert response.status_code == 422, path
        assert _error(response)["code"] == "batch_invalid", path


def test_event_stream_skips_unchanged_payloads(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    payloads = iter(
        [
            {"status": "running", "progress": 1, "stage": "render"},
            {"status": "running", "progress": 1, "stage": "render"},
            {"status": "succeeded", "progress": 100, "stage": "done"},
        ]
    )

    class FakeJob:
        def to_dict(self):
            return next(payloads)

    monkeypatch.setattr(manager, "get", lambda job_id: FakeJob())
    with client.stream("GET", f"/api/v1/jobs/{job.job_id}/events") as response:
        assert response.status_code == 200
        body = b"".join(response.iter_bytes())
    assert body.count(b"data: ") == 2
    assert b'"status": "succeeded"' in body


def test_preview_render_frame_and_waveform_paths(monkeypatch, tmp_path: Path) -> None:
    from videoflow.api import routes as routes_module

    client, manager = _client(monkeypatch, tmp_path)
    (tmp_path / "source.mp4").write_bytes(b"source")
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}"

    preview = job.output / "preview" / "preview.mp4"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"preview")
    from videoflow.application.previews import preview_key, preview_manifest_path

    preview_manifest_path(job).write_text(
        '{"key": "' + preview_key(job) + '", "revision": 1}', encoding="utf-8"
    )
    cached = client.post(f"{base}/preview")
    assert cached.status_code == 200
    assert cached.json()["status"] == "ready"
    assert client.get(f"{base}/preview/status").json()["status"] == "ready"
    assert client.get(f"{base}/preview/file").status_code == 200
    assert client.get(f"{base}/render/status").json()["status"] in {"idle", "ready"}
    missing_render = client.get(f"{base}/render/file")
    assert missing_render.status_code == 404
    assert _error(missing_render)["code"] == "render_not_found"

    monkeypatch.setattr(routes_module, "build_preview", lambda target: preview)
    forced = client.post(f"{base}/preview", params={"force": True})
    assert forced.status_code == 200
    assert forced.json()["status"] == "ready"

    class BrokenFFmpeg:
        def render_thumbnail(self, *args, **kwargs):
            raise RuntimeError("ffmpeg is unavailable")

    monkeypatch.setattr(routes_module, "FFmpegAdapter", BrokenFFmpeg)
    frame = client.get(f"{base}/frame", params={"time": 1.0, "height": 120})
    assert frame.status_code == 422
    assert _error(frame)["code"] == "frame_failed"
    frames = client.get(f"{base}/frames", params={"count": 1, "height": 120})
    assert frames.status_code == 422
    assert _error(frames)["code"] == "frame_failed"

    class GoodFFmpeg:
        def render_thumbnail(self, source, target, **kwargs):
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            Path(target).write_bytes(b"jpeg")

    monkeypatch.setattr(routes_module, "FFmpegAdapter", GoodFFmpeg)
    rendered = client.get(f"{base}/frame", params={"time": 0.5, "height": 100})
    assert rendered.status_code == 200
    assert rendered.headers["content-type"] == "image/jpeg"
    reused = client.get(f"{base}/frame", params={"time": 0.5, "height": 100})
    assert reused.status_code == 200
    cached_frames = client.get(
        f"{base}/frames", params={"start": 0.5, "count": 1, "height": 100}
    )
    assert cached_frames.status_code == 200
    assert cached_frames.json()["frames"][0]["cached"] is True

    def fail_peaks(*args, **kwargs):
        raise ValueError("bad audio stream")

    monkeypatch.setattr(routes_module, "peaks_for_range", fail_peaks)
    waveform = client.get(f"{base}/timeline/waveform")
    assert waveform.status_code == 422
    assert _error(waveform)["code"] == "waveform_failed"


def test_timeline_etag_lock_overlay_comment_and_state_paths(
    monkeypatch, tmp_path: Path
) -> None:
    from videoflow.api import routes as routes_module
    from videoflow.domain.state import (
        AudioSegment,
        ProjectState,
        Sentence,
        VideoSegment,
    )

    client, manager = _client(monkeypatch, tmp_path)
    (tmp_path / "source.mp4").write_bytes(b"source")
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}"

    timeline = client.get(f"{base}/timeline")
    assert timeline.status_code == 200
    etag = timeline.headers["etag"]
    assert client.get(f"{base}/timeline", headers={"if-none-match": etag}).status_code == 304
    matched = client.patch(
        f"{base}/timeline",
        json={"clip_id": "v1", "action": "move", "delta_sec": 0.1},
        headers={"if-match": etag},
    )
    assert matched.status_code == 200, matched.text
    conflict = client.patch(
        f"{base}/timeline",
        json={"clip_id": "v1", "action": "move", "delta_sec": 0.1},
        headers={"if-match": '"timeline-999"'},
    )
    assert conflict.status_code == 412
    assert _error(conflict)["code"] == "precondition_failed"

    faded = client.patch(
        f"{base}/timeline/clip/v1",
        json={"fade_in_sec": 0.25, "fade_out_sec": 0.5},
    )
    assert faded.status_code == 200, faded.text
    payload = client.get(f"{base}/timeline").json()
    assert payload["audio"][0]["fade_in_sec"] == 0.25
    assert payload["audio"][0]["fade_out_sec"] == 0.5

    plain = client.patch(
        f"{base}/timeline/clip/v1", json={"transition_type": "none"}
    )
    assert plain.status_code == 200, plain.text
    assert client.get(f"{base}/timeline").json()["video"][0]["transition"] is None

    locked = client.put(
        f"{base}/timeline/tracks/video",
        json={"muted": False, "locked": True, "solo": False},
    )
    assert locked.status_code == 200
    assert locked.json()["tracks"]["video"]["locked"] is True
    blocked = client.patch(
        f"{base}/timeline", json={"clip_id": "v1", "action": "move", "delta_sec": 0.1}
    )
    assert blocked.status_code == 409
    assert _error(blocked)["code"] == "state_not_ready"
    assert client.put(
        f"{base}/timeline/tracks/video",
        json={"muted": False, "locked": False, "solo": False},
    ).status_code == 200

    denied = client.post(
        f"{base}/timeline/overlays",
        json={"path": "/etc/hosts", "start_sec": 0.0, "duration_sec": 1.0},
    )
    assert denied.status_code == 403
    assert _error(denied)["code"] == "path_not_allowed"
    unknown_overlay = client.delete(f"{base}/timeline/overlays/missing")
    assert unknown_overlay.status_code == 409
    assert _error(unknown_overlay)["code"] == "state_not_ready"
    overlay_file = tmp_path / "overlay.png"
    overlay_file.write_bytes(b"png")
    created_overlay = client.post(
        f"{base}/timeline/overlays",
        json={
            "overlay_id": "ov1",
            "path": str(overlay_file),
            "start_sec": 0.0,
            "duration_sec": 1.0,
        },
    )
    assert created_overlay.status_code == 201, created_overlay.text
    assert created_overlay.json()["overlays"][0]["overlay_id"] == "ov1"
    removed_overlay = client.delete(f"{base}/timeline/overlays/ov1")
    assert removed_overlay.status_code == 200
    assert removed_overlay.json()["overlays"] == []

    marker = client.post(f"{base}/timeline/markers", json={"time_sec": 1.0, "label": "m"})
    assert marker.status_code == 201
    marker_id = marker.json()["markers"][0]["id"]
    assert client.delete(f"{base}/timeline/markers/{marker_id}").status_code == 200
    comment = client.post(
        f"{base}/timeline/comments", json={"clip_id": "v1", "text": "look here"}
    )
    assert comment.status_code == 201
    comment_id = comment.json()["comments"][0]["id"]
    assert client.delete(f"{base}/timeline/comments/{comment_id}").status_code == 200

    calls = {"count": 0}

    def fake_thumbnail(self, source, destination, **kwargs):
        calls["count"] += 1
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(b"jpeg")

    monkeypatch.setattr(routes_module.FFmpegAdapter, "render_thumbnail", fake_thumbnail)
    first = client.get(f"{base}/clips/v1/thumbnail")
    second = client.get(f"{base}/clips/v1/thumbnail")
    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 1

    def noop_thumbnail(self, source, destination, **kwargs):
        return None

    monkeypatch.setattr(routes_module.FFmpegAdapter, "render_thumbnail", noop_thumbnail)
    missing_clip_image = client.get(f"{base}/clips/v2/thumbnail")
    assert missing_clip_image.status_code == 404
    assert _error(missing_clip_image)["code"] == "clip_thumbnail_not_found"

    state = ProjectState.model_validate_json(
        (job.output / "project_state.json").read_text(encoding="utf-8")
    )
    state.audio_segments.append(
        AudioSegment(
            clip_id="audio-only",
            source_in_sample=0,
            source_out_sample=1000,
            timeline_in_sample=0,
            timeline_out_sample=1000,
        )
    )
    state.video_segments.append(
        VideoSegment(
            clip_id="video-only",
            source_in_frame=0,
            source_out_frame=10,
            timeline_in_frame=0,
            timeline_out_frame=10,
        )
    )
    state.transcript = [
        Sentence(id=0, start_sample=0, end_sample=1000, text="one", speaker=0),
        Sentence(id=1, start_sample=1000, end_sample=2000, text="two", speaker=0),
    ]
    (job.output / "project_state.json").write_text(state.model_dump_json())
    audio_only = client.patch(
        f"{base}/timeline/clip/audio-only", json={"fade_in_sec": 0.1}
    )
    assert audio_only.status_code == 200, audio_only.text
    video_only = client.patch(f"{base}/timeline/clip/video-only", json={"scale": 1.1})
    assert video_only.status_code == 200, video_only.text
    caption = client.patch(f"{base}/captions/1", json={"text": "second"})
    assert caption.status_code == 200, caption.text
    assert caption.json()["text"] == "second"

    (job.output / "project_state.json").write_text("{broken", encoding="utf-8")
    invalid_edit = client.patch(
        f"{base}/timeline", json={"clip_id": "v1", "action": "move", "delta_sec": 0.1}
    )
    assert invalid_edit.status_code == 422
    assert _error(invalid_edit)["code"] == "timeline_invalid"
    invalid_state = client.get(f"{base}/state")
    assert invalid_state.status_code == 500
    assert _error(invalid_state)["code"] == "state_invalid"

    (job.output / "project_state.json").unlink()
    missing_state = client.get(f"{base}/timeline")
    assert missing_state.status_code == 409
    assert _error(missing_state)["code"] == "state_not_ready"
    missing_state_doc = client.get(f"{base}/state")
    assert missing_state_doc.status_code == 404
    assert _error(missing_state_doc)["code"] == "state_not_found"


def test_short_download_index_and_thumbnail_edge_cases(monkeypatch, tmp_path: Path) -> None:
    from tests.contract.test_api_media_routes import _short_job

    client, job, _media, _thumb, outside = _short_job(monkeypatch, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}/shorts"

    out_of_range = client.get(f"{base}/99/file")
    assert out_of_range.status_code == 404
    assert _error(out_of_range)["code"] == "shorts_not_found"
    job.result["shorts"][0]["path"] = str(outside)
    outside_file = client.get(f"{base}/0/file")
    assert outside_file.status_code == 404
    assert _error(outside_file)["code"] == "short_file_not_found"

    out_of_range_thumb = client.get(f"{base}/99/thumbnail")
    assert out_of_range_thumb.status_code == 404
    assert _error(out_of_range_thumb)["code"] == "shorts_not_found"
    job.result["shorts"][0]["thumbnail"] = ""
    empty_thumb = client.get(f"{base}/0/thumbnail")
    assert empty_thumb.status_code == 404
    assert _error(empty_thumb)["code"] == "thumbnail_not_found"


def test_admin_models_services_and_system_paths(monkeypatch, tmp_path: Path) -> None:
    from videoflow.api import routes as routes_module

    client, _manager = _client(monkeypatch, tmp_path)
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)

    restart = client.post("/api/v1/system/restart")
    assert restart.status_code == 409
    assert _error(restart)["code"] == "service_control_unavailable"
    shutdown = client.post("/api/v1/system/shutdown")
    assert shutdown.status_code == 409
    assert _error(shutdown)["code"] == "service_control_unavailable"

    client.app.state.uvicorn_server = SimpleNamespace(should_exit=False)
    restarted = client.post("/api/v1/system/restart")
    assert restarted.status_code == 200
    assert restarted.json()["action"] == "restart"
    assert client.app.state.uvicorn_server.should_exit is True
    client.app.state.uvicorn_server.should_exit = False
    stopped = client.post("/api/v1/system/shutdown")
    assert stopped.status_code == 200
    assert stopped.json()["action"] == "shutdown"

    empty = client.post("/api/v1/system/restore", content=b"")
    assert empty.status_code == 422
    assert _error(empty)["code"] == "empty_backup"
    invalid = client.post("/api/v1/system/restore", content=b"not a zip")
    assert invalid.status_code == 422
    assert _error(invalid)["code"] == "invalid_backup"

    monkeypatch.setattr(routes_module, "find_binary", lambda name: None)
    doctor = client.get("/api/v1/system/doctor")
    assert doctor.status_code == 200
    assert doctor.json()["checks"]["ffmpeg"]["found"] is False
    assert doctor.json()["ok"] is False

    routes_module.append_server_log("coverage smoke")
    bundle = client.get("/api/v1/system/support-bundle")
    assert bundle.status_code == 200
    names = set(zipfile.ZipFile(io.BytesIO(bundle.content)).namelist())
    assert {"doctor.json", "settings.json", "server.log"} <= names
    backup = client.get("/api/v1/system/backup")
    assert backup.status_code == 200
    restored = client.post("/api/v1/system/restore", content=backup.content)
    assert restored.status_code == 200, restored.text
    assert restored.json()["ok"] is True
    assert "videoflow.db" in restored.json()["restored"]
    assert client.get("/api/v1/system/metrics").status_code == 200
    assert client.get("/api/v1/metrics/cost").status_code == 200

    assert client.get("/api/v1/services/definitions").status_code == 200
    missing_status = client.get("/api/v1/services/definitions/missing/status")
    assert missing_status.status_code == 409
    assert _error(missing_status)["code"] == "state_not_ready"
    assert client.get("/api/v1/services/definitions/missing/logs").status_code == 409
    missing_start = client.post("/api/v1/services/definitions/missing/start")
    assert missing_start.status_code == 409
    assert _error(missing_start)["code"] == "state_not_ready"
    assert client.post("/api/v1/services/definitions/missing/stop").status_code == 200
    missing_delete = client.delete("/api/v1/services/definitions/missing")
    assert missing_delete.status_code == 409
    assert _error(missing_delete)["code"] == "state_not_ready"

    def fail_stop(service_id):
        from videoflow.domain.errors import StateNotReadyError

        raise StateNotReadyError("cannot stop service")

    monkeypatch.setattr(routes_module, "stop_service", fail_stop)
    stop_failed = client.post("/api/v1/services/definitions/anything/stop")
    assert stop_failed.status_code == 409
    assert _error(stop_failed)["code"] == "state_not_ready"

    assert client.get("/api/v1/services").status_code == 200
    assert client.get("/api/v1/services/log").status_code == 200
    assert client.post("/api/v1/services/cleanup").status_code == 200

    monkeypatch.setattr(
        routes_module,
        "discover_services",
        lambda current_pid=None: [SimpleNamespace(pid=os.getpid(), current=True, protected=False)],
    )
    protected = client.post(f"/api/v1/services/{os.getpid()}/stop")
    assert protected.status_code == 409
    assert _error(protected)["code"] == "service_protected"
    monkeypatch.setattr(
        routes_module,
        "discover_services",
        lambda current_pid=None: [SimpleNamespace(pid=4242, current=False, protected=False)],
    )
    monkeypatch.setattr(routes_module, "stop_service_pid", lambda pid: True)
    stopped = client.post("/api/v1/services/4242/stop")
    assert stopped.status_code == 200
    assert stopped.json()["stopped"] is True

    assert client.get("/api/v1/models").status_code == 200
    unknown_install = client.post("/api/v1/models/unknown/install", json={})
    assert unknown_install.status_code == 409
    assert _error(unknown_install)["code"] == "state_not_ready"
    started = client.post("/api/v1/models/unknown/download", json={})
    assert started.status_code == 202
    assert started.json()["download"]["model_id"] == "unknown"
    listed = client.get("/api/v1/models/downloads")
    assert listed.status_code == 200
    assert "unknown" in [item["model_id"] for item in listed.json()["downloads"]]
    cancelled = client.delete("/api/v1/models/downloads/unknown")
    assert cancelled.status_code == 200
    assert cancelled.json()["download"]["model_id"] == "unknown"

    local_missing = client.post(
        "/api/v1/models/local", json={"id": "m", "path": str(tmp_path / "gone")}
    )
    assert local_missing.status_code == 409
    assert _error(local_missing)["code"] == "state_not_ready"
    verify_missing = client.post("/api/v1/models/unknown/verify")
    assert verify_missing.status_code == 409
    assert _error(verify_missing)["code"] == "state_not_ready"
    remove_missing = client.delete("/api/v1/models/unknown")
    assert remove_missing.status_code == 409
    assert _error(remove_missing)["code"] == "state_not_ready"

    backup_failed = client.post("/api/v1/maintenance/backup")
    assert backup_failed.status_code in {200, 500}

    from videoflow.application import backups

    def fail_backup():
        raise OSError("cannot write backup")

    monkeypatch.setattr(backups, "scheduled_backup", fail_backup)
    broken_backup = client.post("/api/v1/maintenance/backup")
    assert broken_backup.status_code == 500
    assert _error(broken_backup)["code"] == "backup_failed"


def test_read_only_inventory_endpoints(monkeypatch, tmp_path: Path) -> None:
    from videoflow.api import routes as routes_module

    client, _manager = _client(monkeypatch, tmp_path)
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(routes_module, "find_binary", lambda name: None)
    paths = [
        "/api/v1/jobs",
        "/api/v1/batches",
        "/api/v1/capabilities",
        "/api/v1/steps",
        "/api/v1/node-options",
        "/api/v1/recipes",
        "/api/v1/providers",
        "/api/v1/node-presets",
        "/api/v1/schedules",
        "/api/v1/publish/targets",
        "/api/v1/publish/queue",
        "/api/v1/project-templates",
        "/api/v1/brand-templates",
        "/api/v1/projects",
        "/api/v1/assets",
        "/api/v1/assets/music",
        "/api/v1/assets/sfx",
        "/api/v1/assets/images",
        "/api/v1/assets/fonts",
        "/api/v1/models",
        "/api/v1/models/downloads",
        "/api/v1/fs/roots",
        "/api/v1/services",
        "/api/v1/services/log",
        "/api/v1/services/definitions",
        "/api/v1/voice-clone/status",
        "/api/v1/voice-clone/profiles",
        "/api/v1/metrics/cost",
        "/api/v1/system/metrics",
        "/api/v1/settings",
        "/api/v1/settings/export",
        "/api/v1/system",
        "/api/v1/plugins",
        "/api/v1/presets",
    ]
    for path in paths:
        assert client.get(path).status_code == 200, path
    runs = client.get("/api/v1/runs", params={"output": str(tmp_path)})
    assert runs.status_code == 200
    assert runs.json()["runs"] == []
    denied_runs = client.get("/api/v1/runs", params={"output": "/definitely/not/allowed"})
    assert denied_runs.status_code == 403
    assert _error(denied_runs)["code"] == "path_not_allowed"

    bad_preset = client.put("/api/v1/presets/Bad_Name", json={"name": "Bad_Name"})
    assert bad_preset.status_code == 422
    assert _error(bad_preset)["code"] == "invalid_preset_name"
    invalid_preset = client.put("/api/v1/presets/bad-body", json={"name": "bad-body"})
    assert invalid_preset.status_code == 422
    assert _error(invalid_preset)["code"] == "preset_invalid"

    missing_schedule = client.delete("/api/v1/schedules/missing")
    assert missing_schedule.status_code == 409
    assert _error(missing_schedule)["code"] == "state_not_ready"
    missing_run = client.post("/api/v1/schedules/missing/run")
    assert missing_run.status_code == 409
    assert _error(missing_run)["code"] == "state_not_ready"

    presets_dir = tmp_path / "home" / "presets"
    presets_dir.mkdir(parents=True, exist_ok=True)
    (presets_dir / "broken.json").write_text("{broken", encoding="utf-8")
    broken_presets = client.get("/api/v1/presets")
    assert broken_presets.status_code == 422
    assert _error(broken_presets)["code"] == "preset_invalid"

    def fail_roots():
        from videoflow.domain.errors import FilesystemError

        raise FilesystemError("cannot resolve roots")

    monkeypatch.setattr(routes_module, "roots_payload", fail_roots)
    broken_roots = client.get("/api/v1/fs/roots")
    assert broken_roots.status_code == 500
    assert _error(broken_roots)["code"] == "filesystem_error"


def test_copilot_and_assistant_error_paths(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application import assistant, copilot, llm_factory
    from videoflow.domain.errors import RecipeError

    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}"

    monkeypatch.setattr(llm_factory, "build_llm", lambda: object())

    def reject_recipe(client_obj, prompt):
        raise RecipeError("unsupported recipe request")

    monkeypatch.setattr(copilot, "propose_recipe", reject_recipe)
    rejected = client.post("/api/v1/copilot/recipe", json={"prompt": "make a video"})
    assert rejected.status_code == 422
    assert _error(rejected)["code"] == "recipe_invalid"

    monkeypatch.setattr(
        copilot,
        "propose_timeline_edits",
        lambda *args, **kwargs: [
            {"clip_id": "v1", "action": "move", "delta_sec": 0.1}
        ],
    )
    applied = client.post(
        f"{base}/copilot/timeline", json={"prompt": "shift v1", "apply": True}
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied"] is True
    assert applied.json()["revision"] == 2
    assert len(applied.json()["edits"]) == 1
    previewed = client.post(
        f"{base}/copilot/timeline", json={"prompt": "shift v1", "apply": False}
    )
    assert previewed.status_code == 200, previewed.text
    assert previewed.json()["applied"] is False
    assert previewed.json()["revision"] == 2

    turns = [
        assistant.Turn(
            message="reading", actions=[assistant.Action(id="a1", tool="list_recipes")]
        ),
        assistant.Turn(message="finished", actions=[]),
    ]
    monkeypatch.setattr(assistant, "plan", lambda *args, **kwargs: turns.pop(0))
    turn = client.post(f"{base}/assistant", json={"prompt": "what recipes exist?"})
    assert turn.status_code == 200, turn.text
    assert turn.json()["message"] == "finished"
    assert turn.json()["observations"][0]["tool"] == "a1"
    assert client.get(f"{base}/assistant/history").status_code == 200

    assistant.save_pending(
        job.output,
        assistant.PendingPlan(
            approval_id="other-job",
            job_id="not-this-job",
            prompt="p",
            message="m",
            actions=[],
            created_at=assistant.now(),
        ),
    )
    mismatch = client.post(
        f"{base}/assistant/approve", json={"approval_id": "other-job"}
    )
    assert mismatch.status_code == 409
    assert "another job" in _error(mismatch)["message"]


def test_doctor_defensive_environment_branches(monkeypatch, tmp_path: Path) -> None:
    from videoflow.api import routes as routes_module

    client, _manager = _client(monkeypatch, tmp_path)
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)

    script = tmp_path / "fake-ffmpeg"
    script.write_text("#!/bin/sh\necho 'ffmpeg version 9.9'\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setattr(routes_module, "find_binary", lambda name: str(script))
    present = client.get("/api/v1/system/doctor")
    assert present.status_code == 200
    assert present.json()["checks"]["ffmpeg"]["version"] == "ffmpeg version 9.9"
    capabilities = present.json()["checks"]["ffmpeg_capabilities"]
    assert capabilities["libx264"] is False
    assert capabilities["loudnorm"] is False

    monkeypatch.setattr(routes_module, "find_binary", lambda name: None)

    class BrokenCuda:
        @staticmethod
        def get_cuda_device_count():
            raise RuntimeError("no cuda")

    class BrokenOnnx:
        @staticmethod
        def get_available_providers():
            raise RuntimeError("no onnx")

    class BrokenSqlite:
        @staticmethod
        def connect(*args, **kwargs):
            raise RuntimeError("no database")

    monkeypatch.setitem(sys.modules, "ctranslate2", BrokenCuda())
    monkeypatch.setitem(sys.modules, "onnxruntime", BrokenOnnx())
    monkeypatch.setitem(sys.modules, "sqlite3", BrokenSqlite())
    response = client.get("/api/v1/system/doctor")
    assert response.status_code == 200
    checks = response.json()["checks"]
    assert checks["cuda_devices"] == 0
    assert checks["onnx_providers"] == []
    assert checks["database"]["integrity"] == "unavailable"


def test_route_error_boundaries_with_service_failures(monkeypatch, tmp_path: Path) -> None:
    from videoflow.api import routes as routes_module
    from videoflow.domain.errors import StateNotReadyError

    client, _manager = _client(monkeypatch, tmp_path)

    def explode(*args, **kwargs):
        raise StateNotReadyError("service layer refused")

    provider = {
        "id": "boundary",
        "name": "Boundary",
        "capability": "llm",
        "base_url": "http://127.0.0.1:9/v1",
        "model": "boundary",
    }
    monkeypatch.setattr(routes_module, "upsert_provider", explode)
    failed_provider = client.put("/api/v1/providers/boundary", json=provider)
    assert failed_provider.status_code == 409
    assert _error(failed_provider)["code"] == "state_not_ready"

    monkeypatch.setattr(routes_module, "upsert_schedule", explode)
    failed_schedule = client.put(
        "/api/v1/schedules/boundary",
        json={"id": "boundary", "recipe_id": "youtube_talking_head"},
    )
    assert failed_schedule.status_code == 409
    assert _error(failed_schedule)["code"] == "state_not_ready"

    monkeypatch.setattr(routes_module, "save_definition", explode)
    failed_service = client.put(
        "/api/v1/services/definitions/boundary",
        json={"id": "boundary", "name": "Boundary", "command": "true"},
    )
    assert failed_service.status_code == 409
    assert _error(failed_service)["code"] == "state_not_ready"

    monkeypatch.setattr(routes_module, "create_project", explode)
    failed_project = client.post("/api/v1/projects", json={"name": "Boundary"})
    assert failed_project.status_code == 409
    assert _error(failed_project)["code"] == "state_not_ready"
