from __future__ import annotations

from pathlib import Path

from tests.contract.api_helpers import _client, _job


def test_step_outputs_are_listed_read_saved_and_downloaded(
    monkeypatch, tmp_path: Path
) -> None:
    from videoflow.application.step_outputs import write_step_outputs
    from videoflow.steps.base import PortSpec

    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    media = job.output / "media.json"
    media.write_text('{"ok": true}\n', encoding="utf-8")
    write_step_outputs(
        job.output,
        step_id="ingest",
        step_type="ingest",
        status="executed",
        fingerprint="fp",
        ports={"media": {"path": str(media)}},
        port_specs=[PortSpec("media", "Media", "media", "media")],
        hashes={"media": "hash"},
        files=[str(media)],
        elapsed_ms=3,
    )
    base = f"/api/v1/jobs/{job.job_id}/steps/ingest"
    listed = client.get(f"{base}/outputs")
    assert listed.status_code == 200, listed.text
    assert listed.json()["ports"][0]["id"] == "media"
    port = client.get(f"{base}/outputs/media")
    assert port.status_code == 200, port.text
    assert port.json()["port"]["value"]["path"] == str(media)
    download = client.get(f"{base}/files/media.json")
    assert download.status_code == 200
    target = tmp_path / "saved"
    saved = client.post(f"{base}/save", json={"target_dir": str(target)})
    assert saved.status_code == 200, saved.text
    assert (target / "ingest-outputs.json").is_file()
    assert client.get(f"/api/v1/jobs/{job.job_id}/steps/nope/outputs").status_code == 404


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
