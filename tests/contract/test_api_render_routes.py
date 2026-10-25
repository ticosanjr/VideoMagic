from __future__ import annotations

from pathlib import Path

from tests.contract.test_api_timeline import _client, _job
from videoflow.application.previews import PreviewState
from videoflow.application.render_queue import RenderState


def test_render_status_files_and_start(monkeypatch, tmp_path: Path) -> None:
    from videoflow.api import routes as routes_module

    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}/render"

    assert client.get(f"{base}/status").json()["status"] == "idle"
    assert client.get(f"{base}/file").status_code == 404
    assert client.post(f"{base}/cancel").status_code == 404

    render = job.output / "render" / "timeline.mp4"
    render.parent.mkdir(parents=True, exist_ok=True)
    render.write_bytes(b"render")
    assert client.get(f"{base}/status").json()["status"] == "ready"
    assert client.get(f"{base}/file").status_code == 200

    state = RenderState(job_id=str(job.job_id), status="rendering", percent=10)
    monkeypatch.setattr(routes_module.renders, "start", lambda item: state)
    monkeypatch.setattr(routes_module.renders, "get", lambda job_id: state)
    monkeypatch.setattr(routes_module.renders, "cancel", lambda job_id: state)
    assert client.post(base).status_code == 202
    assert client.get(f"{base}/status").json()["percent"] == 10
    assert client.post(f"{base}/cancel").status_code == 200

    other_client, other_manager = _client(monkeypatch, tmp_path)
    queued_job = _job(other_manager, tmp_path)
    other_manager.cancel(str(queued_job.job_id))
    queued_job.status = "queued"
    assert other_client.post(f"/api/v1/jobs/{queued_job.job_id}/render").status_code == 409


def test_preview_status_download_and_creation(monkeypatch, tmp_path: Path) -> None:
    from videoflow.api import routes as routes_module

    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}/preview"

    assert client.get(f"{base}/status").json()["status"] == "idle"
    assert client.get(f"{base}/file").status_code == 404
    assert client.post(f"{base}/cancel").status_code == 404

    preview = job.output / "preview" / "preview.mp4"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"preview")
    assert client.get(f"{base}/status").json()["status"] == "ready"
    assert client.get(f"{base}/file").status_code == 200
    assert client.post(base).json()["status"] == "ready"

    state = PreviewState(job_id=str(job.job_id), status="rendering", percent=25)
    monkeypatch.setattr(routes_module.previews, "start", lambda item: state)
    monkeypatch.setattr(routes_module.previews, "get", lambda job_id: state)
    monkeypatch.setattr(routes_module.previews, "cancel", lambda job_id: state)
    assert client.post(f"{base}?background=true").json()["status"]["percent"] == 25
    assert client.get(f"{base}/status").json()["percent"] == 25
    assert client.post(f"{base}/cancel").status_code == 200

    forced = job.output / "preview" / "forced.mp4"

    def fake_build(job) -> None:
        forced.write_bytes(b"forced")

    monkeypatch.setattr(routes_module, "build_preview", fake_build)
    assert client.post(f"{base}?force=true").status_code == 200
    assert forced.is_file()
