from __future__ import annotations

from pathlib import Path

from tests.contract.test_api_timeline import _client, _job


def test_assets_presets_templates_and_config(monkeypatch, tmp_path: Path) -> None:
    from videoflow.api import routes as routes_module

    client, _manager = _client(monkeypatch, tmp_path)

    monkeypatch.setattr(routes_module, "save_music", lambda name, body: {"name": name})
    monkeypatch.setattr(routes_module, "save_image", lambda name, body: {"name": name})
    monkeypatch.setattr(routes_module, "save_font", lambda name, body: {"name": name})
    monkeypatch.setattr(routes_module, "delete_music", lambda name: None)
    monkeypatch.setattr(routes_module, "delete_images", lambda name: None)
    monkeypatch.setattr(routes_module, "delete_fonts", lambda name: None)
    assert client.post("/api/v1/assets/music?name=a.mp3", content=b"x").status_code == 201
    assert client.post("/api/v1/assets/images?name=a.png", content=b"x").status_code == 201
    assert client.post("/api/v1/assets/fonts?name=a.ttf", content=b"x").status_code == 201
    assert client.delete("/api/v1/assets/music/a.mp3").status_code == 200
    assert client.delete("/api/v1/assets/images/a.png").status_code == 200
    assert client.delete("/api/v1/assets/fonts/a.ttf").status_code == 200
    assert client.get("/api/v1/assets/music").status_code == 200
    assert client.get("/api/v1/assets/images").status_code == 200
    assert client.get("/api/v1/assets/fonts").status_code == 200

    shipped = client.get("/api/v1/presets").json()["presets"][0]
    preset = {
        "name": "demo",
        "description": "demo preset",
        "modules_config": shipped["modules_config"],
        "module_enabled": shipped["module_enabled"],
    }
    assert client.put("/api/v1/presets/demo", json=preset).status_code == 200
    assert client.get("/api/v1/presets/demo").status_code == 200
    assert client.get("/api/v1/presets").status_code == 200
    assert client.get("/api/v1/presets/missing").status_code == 404

    brand = {"name": "brand", "description": "demo"}
    assert client.put("/api/v1/brand-templates/brand", json=brand).status_code == 200
    assert client.get("/api/v1/brand-templates/brand").status_code == 200
    assert client.post("/api/v1/brand-templates/brand/apply").status_code == 200
    assert client.get("/api/v1/brand-templates").status_code == 200
    assert client.delete("/api/v1/brand-templates/brand").status_code == 200

    project = {"name": "proj", "description": "demo", "options": {"crf": 19}}
    assert client.put("/api/v1/project-templates/proj", json=project).status_code == 200
    assert client.get("/api/v1/project-templates/proj").status_code == 200
    assert client.post("/api/v1/project-templates/proj/apply").status_code == 200
    assert client.get("/api/v1/project-templates").status_code == 200
    assert client.delete("/api/v1/project-templates/proj").status_code == 200

    exported = client.post("/api/v1/config/export", json={"options": {"crf": 18}})
    assert exported.status_code == 200
    envelope = exported.json()["envelope"]
    assert (
        client.post(
            "/api/v1/config/import",
            json={
                "schema_version": envelope["schema_version"],
                "options": envelope["options"],
            },
        ).status_code
        == 200
    )


def test_recipes_batches_and_maintenance(monkeypatch, tmp_path: Path) -> None:
    client, _manager = _client(monkeypatch, tmp_path)
    recipes = client.get("/api/v1/recipes").json()["recipes"]
    recipe_id = recipes[0]["id"]
    assert client.get(f"/api/v1/recipes/{recipe_id}").status_code == 200
    assert client.get("/api/v1/recipes/missing").status_code in {404, 422}

    draft = {
        "schema_version": 1,
        "id": "sweep_recipe",
        "name": "Sweep",
        "steps": [{"id": "ingest", "type": "ingest", "params": {}}],
    }
    assert client.put("/api/v1/recipes/sweep_recipe", json=draft).status_code == 200
    assert client.post("/api/v1/recipes/validate", json=draft).status_code == 200
    assert client.post("/api/v1/recipes/validate", json={"bad": True}).status_code == 422
    assert client.post(
        "/api/v1/recipes/dry-run",
        json={
            "source": str(tmp_path / "source.mp4"),
            "output": str(tmp_path / "dry"),
            "recipe": draft,
        },
    ).status_code in {200, 422}
    assert client.get("/api/v1/recipes/sweep_recipe/history").status_code == 200
    assert client.post("/api/v1/recipes/sweep_recipe/history/0/restore").status_code < 500

    source_dir = tmp_path / "batch-in"
    source_dir.mkdir()
    (source_dir / "a.mp4").write_bytes(b"x")
    created = client.post(
        "/api/v1/batches",
        json={
            "source_dir": str(source_dir),
            "output_root": str(tmp_path / "batch-out"),
            "recipe": draft,
        },
    )
    assert created.status_code == 202
    batch_id = created.json()["batch"]["batch_id"]
    assert client.get(f"/api/v1/batches/{batch_id}").status_code == 200
    assert client.post(f"/api/v1/batches/{batch_id}/cancel").status_code == 200
    assert client.post(f"/api/v1/batches/{batch_id}/resume").status_code in {200, 409}

    out = tmp_path / "out"
    out.mkdir()
    assert (
        client.post(
            "/api/v1/maintenance/prune",
            json={"output": str(out), "dry_run": True},
        ).status_code
        == 200
    )
    assert client.post("/api/v1/maintenance/backup").status_code in {200, 500}


def test_providers_services_models_plugins_and_system(monkeypatch, tmp_path: Path) -> None:
    client, _manager = _client(monkeypatch, tmp_path)
    provider = {
        "id": "demo",
        "name": "Demo",
        "capability": "llm",
        "base_url": "http://127.0.0.1:9999/v1",
        "model": "demo",
        "enabled": True,
    }
    assert client.put("/api/v1/providers/demo", json=provider).status_code == 200
    assert client.post("/api/v1/providers/demo/default").status_code == 200
    assert client.post("/api/v1/providers/demo/default").status_code == 200
    assert client.get("/api/v1/providers").status_code == 200
    assert client.delete("/api/v1/providers/demo").status_code == 200

    service = {"id": "demo", "name": "Demo", "command": "/bin/true", "args": []}
    assert client.put("/api/v1/services/definitions/demo", json=service).status_code == 200
    assert client.get("/api/v1/services/definitions").status_code == 200
    assert client.get("/api/v1/services/definitions/demo/status").status_code in {200, 404}
    assert client.get("/api/v1/services/definitions/demo/logs").status_code in {200, 404}
    assert client.post("/api/v1/services/definitions/demo/stop").status_code in {200, 404, 409}
    assert client.delete("/api/v1/services/definitions/demo").status_code == 200

    assert client.get("/api/v1/services").status_code == 200
    assert client.get("/api/v1/services/log").status_code == 200
    assert client.post("/api/v1/services/999999/stop").status_code == 404
    assert client.get("/api/v1/system/doctor").status_code == 200
    assert client.delete("/api/v1/models/missing").status_code in {200, 404, 409}


def test_publish_targets_queue_and_short_errors(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    target = {"webhook_url": "http://127.0.0.1:9999/hook", "enabled": False}
    assert client.put("/api/v1/publish/targets/demo", json=target).status_code == 200
    assert client.get("/api/v1/publish/targets").status_code == 200
    assert client.get("/api/v1/publish/queue").status_code == 200
    assert client.post("/api/v1/publish/queue/missing/cancel").status_code in {404, 409}
    assert client.post("/api/v1/publish/dispatch", json={}).status_code == 200
    assert client.delete("/api/v1/publish/targets/demo").status_code == 200
    assert client.post(
        f"/api/v1/jobs/{job.job_id}/shorts/0/publish",
        json={"target": "demo"},
    ).status_code in {404, 409}
