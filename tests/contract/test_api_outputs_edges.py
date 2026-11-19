from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tests.contract.api_helpers import _client, _job


def _error(response) -> dict:
    payload = response.json()
    detail = payload.get("detail", payload)
    return detail if isinstance(detail, dict) else {"errors": detail}


def test_live_source_routes_and_errors(monkeypatch, tmp_path: Path) -> None:
    from videoflow.api import routes_outputs as routes_module
    from videoflow.application.live_source import LiveSourceState

    client, manager = _client(monkeypatch, tmp_path)
    (tmp_path / "source.mp4").write_bytes(b"source")
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}"

    state = LiveSourceState(status="preparing", reason="probing", path="")

    class Fake:
        def status(self, job, *, height):
            return state

        def start(self, job, *, height):
            return LiveSourceState(status="ready", url="/live", path=str(tmp_path / "x.mp4"))

        def file(self, job, *, height):
            return None

    monkeypatch.setattr(routes_module, "live_sources", Fake())
    assert client.get(f"{base}/live-source/status").json()["live_source"]["status"] == "preparing"
    assert client.post(f"{base}/live-source").json()["live_source"]["status"] == "ready"
    missing = client.get(f"{base}/live-source/file")
    assert missing.status_code == 409
    assert _error(missing)["code"] == "state_not_ready"

    target = tmp_path / "live.mp4"
    target.write_bytes(b"live")
    Fake.file = lambda self, job, *, height: target
    monkeypatch.setattr(routes_module, "live_sources", Fake())
    served = client.get(f"{base}/live-source/file")
    assert served.status_code == 200

    monkeypatch.setattr(routes_module, "live_sources", Fake())
    monkeypatch.setattr(
        routes_module,
        "load_state",
        lambda path: (_ for _ in ()).throw(OSError("bad state")),
    )
    assert client.get(f"{base}/live-source/status").json()["live_source"]["status"] == "preparing"
    monkeypatch.setattr(
        routes_module,
        "load_state",
        lambda path: SimpleNamespace(media_info=SimpleNamespace(height=720)),
    )

    class BrokenFile:
        def file(self, job, *, height):
            raise OSError("bad state")

    monkeypatch.setattr(routes_module, "live_sources", BrokenFile())
    failed = client.get(f"{base}/live-source/file")
    assert failed.status_code == 422
    assert _error(failed)["code"] == "live_source_failed"


def test_source_file_missing_media_and_missing_file(monkeypatch, tmp_path: Path) -> None:
    from videoflow.domain.state import MediaInfo, ProjectState

    client, manager = _client(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}"

    ok = client.get(f"{base}/source/file")
    assert ok.status_code == 200

    state_path = Path(job.result["state_path"])
    state_path.write_text(ProjectState().model_dump_json(), encoding="utf-8")
    no_media = client.get(f"{base}/source/file")
    assert no_media.status_code == 409
    assert _error(no_media)["code"] == "state_not_ready"

    state = ProjectState(
        media_info=MediaInfo(
            source_path=str(tmp_path / "gone.mp4"),
            duration_frames=1,
            fps_num=30,
            fps_den=1,
            width=10,
            height=10,
            audio_sample_rate=48000,
        )
    )
    state_path.write_text(state.model_dump_json(), encoding="utf-8")
    offline = client.get(f"{base}/source/file")
    assert offline.status_code == 409
    assert _error(offline)["code"] == "state_not_ready"


def test_render_and_preview_stale_states(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application import previews as previews_module
    from videoflow.application import render_queue
    from videoflow.application.worker_state import WorkerState

    client, manager = _client(monkeypatch, tmp_path)
    (tmp_path / "source.mp4").write_bytes(b"source")
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}"

    render_queue.renders._items[str(job.job_id)] = WorkerState(
        job_id=str(job.job_id), status="ready"
    )
    stale = client.get(f"{base}/render/status").json()
    assert stale["status"] == "failed"
    assert stale["error_details"]["code"] == "render_stale"

    previews_module.previews._items[str(job.job_id)] = WorkerState(
        job_id=str(job.job_id), status="ready"
    )
    stale_preview = client.get(f"{base}/preview/status").json()
    assert stale_preview["status"] == "stale"
    assert stale_preview["message"] == "Preview is stale"


def test_step_outputs_validation_edges(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    (tmp_path / "source.mp4").write_bytes(b"source")
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}/steps/bad%5Cid"

    assert client.get(f"{base}/outputs").status_code == 422
    assert client.get(f"{base}/outputs/port").status_code == 422
    assert client.get(f"{base}/files/x.txt").status_code == 422
    assert client.post(f"{base}/save", json={"target_dir": str(tmp_path)}).status_code == 422

    good = f"/api/v1/jobs/{job.job_id}/steps/ingest"
    assert client.get(f"{good}/outputs").status_code == 404
    assert client.get(f"{good}/outputs/port").status_code == 404
    assert client.get(f"{good}/files/x.txt").status_code == 404
    assert (
        client.post(f"{good}/save", json={"target_dir": str(tmp_path)}).status_code
        == 404
    )


def test_editable_plan_artifacts_are_saved_atomically(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    (tmp_path / "source.mp4").write_bytes(b"source")
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}"
    plan = job.output / "motion" / "scenes.json"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text('{"scenes": [{"scene_id": "SCENE-0001"}]}\n', encoding="utf-8")
    job.result["artifacts"] = {"motion_scenes": str(plan)}

    updated = client.patch(
        f"{base}/artifacts/motion_scenes",
        json={"payload": {"scenes": [{"scene_id": "SCENE-0001", "title": "New"}]}},
    )
    assert updated.status_code == 200, updated.text
    assert "New" in plan.read_text(encoding="utf-8")
    assert (job.output / "plan-edits.jsonl").is_file()

    invalid = client.patch(
        f"{base}/artifacts/motion_scenes", json={"payload": {"scenes": "bad"}}
    )
    assert invalid.status_code == 422
    assert _error(invalid)["code"] == "artifact_invalid"

    blocked = client.patch(
        f"{base}/artifacts/secret.json", json={"payload": {}}
    )
    assert blocked.status_code == 422
    assert _error(blocked)["code"] == "artifact_not_editable"

    missing = client.patch(
        f"{base}/artifacts/motion_callouts", json={"payload": {"callouts": []}}
    )
    assert missing.status_code == 404
