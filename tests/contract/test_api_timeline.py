from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from videoflow.api.app import create_app
from videoflow.application.jobs import JobManager
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment


def _runner(source: Path, output: Path, **kwargs):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    state = ProjectState(
        media_info=MediaInfo(
            source_path=str(source),
            duration_frames=100,
            fps_num=25,
            fps_den=1,
            width=320,
            height=240,
            audio_sample_rate=48000,
        ),
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_in_frame=0,
                source_out_frame=25,
                timeline_in_frame=0,
                timeline_out_frame=25,
            ),
            VideoSegment(
                clip_id="v2",
                source_in_frame=25,
                source_out_frame=50,
                timeline_in_frame=25,
                timeline_out_frame=50,
            ),
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            ),
            AudioSegment(
                clip_id="v2",
                source_in_sample=48000,
                source_out_sample=96000,
                timeline_in_sample=48000,
                timeline_out_sample=96000,
            ),
        ],
    )
    path = output / "project_state.json"
    path.write_text(state.model_dump_json(), encoding="utf-8")
    return {
        "ok": True,
        "state_path": str(path),
        "artifacts": {},
        "shorts": [],
        "broll_plan": {"Short one": [{"path": "/a.mp4"}, {"path": "/b.mp4"}]},
    }


def _client(monkeypatch, tmp_path: Path) -> tuple[TestClient, JobManager]:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    manager = JobManager(runner=_runner)
    return TestClient(create_app(jobs=manager)), manager


def _job(manager: JobManager, tmp_path: Path):
    job = manager.start(tmp_path / "source.mp4", tmp_path / "out", {})
    for _ in range(300):
        if job.status in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.01)
    assert job.status == "succeeded"
    return job


def test_timeline_split_undo_and_redo(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)

    split = client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline",
        json={"clip_id": "v1", "action": "split", "split_sec": 0.5},
    )
    assert split.status_code == 200, split.text
    assert split.json()["revision"] == 2
    payload = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    assert len(payload["video"]) == 3
    assert payload["can_undo"] is True

    undone = client.post(f"/api/v1/jobs/{job.job_id}/timeline/undo")
    assert undone.status_code == 200, undone.text
    payload = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    assert [clip["id"] for clip in payload["video"]] == ["v1", "v2"]
    assert payload["can_redo"] is True

    redone = client.post(f"/api/v1/jobs/{job.job_id}/timeline/redo")
    assert redone.status_code == 200, redone.text
    assert len(client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()["video"]) == 3


def test_timeline_ripple_delete(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    response = client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline",
        json={"clip_id": "v1", "action": "ripple"},
    )
    assert response.status_code == 200, response.text
    payload = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    assert [clip["id"] for clip in payload["video"]] == ["v2"]
    assert payload["video"][0]["start_sec"] == 0.0


def test_timeline_rejects_split_outside_the_clip(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    response = client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline",
        json={"clip_id": "v2", "action": "split", "split_sec": 0.1},
    )
    assert response.status_code == 422


def test_broll_approval_roundtrip(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    response = client.get(f"/api/v1/jobs/{job.job_id}/broll")
    assert response.status_code == 200
    assert "Short one" in response.json()["plan"]

    saved = client.patch(
        f"/api/v1/jobs/{job.job_id}/broll",
        json={"title": "Short one", "approved": [1], "order": [1, 0]},
    )
    assert saved.status_code == 200, saved.text
    timeline = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    assert timeline["broll_approval"]["Short one"]["approved"] == [1]
    assert timeline["broll_approval"]["Short one"]["order"] == [1, 0]


def test_provider_crud_roundtrip(monkeypatch, tmp_path: Path) -> None:
    client, _ = _client(monkeypatch, tmp_path)
    provider = {
        "id": "local-llm",
        "name": "Local LLM",
        "capability": "llm",
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key_env": "",
        "model": "qwen2.5:7b-instruct",
        "enabled": True,
        "is_default": True,
        "fallback": [],
        "notes": "",
    }
    saved = client.put("/api/v1/providers/local-llm", json=provider)
    assert saved.status_code == 200, saved.text
    listing = client.get("/api/v1/providers").json()
    assert listing["providers"][0]["id"] == "local-llm"
    assert listing["fallbacks"]["llm"][0]["id"] == "local-llm"
    resolved = client.get("/api/v1/providers/resolve", params={"capability": "llm"}).json()
    assert resolved["chain"][0]["id"] == "local-llm"
    removed = client.delete("/api/v1/providers/local-llm")
    assert removed.status_code == 200
    assert client.get("/api/v1/providers").json()["providers"] == []


def test_clip_style_update_roundtrip(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    response = client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline/clip/v1",
        json={
            "transition_type": "fade_to_black",
            "transition_duration_frames": 8,
            "scale": 1.2,
            "fade_in_sec": 0.25,
            "fade_out_sec": 0.5,
        },
    )
    assert response.status_code == 200, response.text
    payload = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    clip = payload["video"][0]
    assert clip["transition"] == "fade_to_black"
    assert clip["transition_frames"] == 8
    assert clip["zoom"] == 1.2
    audio = payload["audio"][0]
    assert audio["fade_in_sec"] == 0.25
    assert audio["fade_out_sec"] == 0.5
    assert payload["revision"] == 2


def test_schedule_crud_and_run_now(monkeypatch, tmp_path: Path) -> None:
    client, _ = _client(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    schedule = {
        "id": "watch-one",
        "kind": "interval",
        "recipe_id": "youtube_talking_head",
        "source": str(source),
        "output": str(tmp_path / "out-scheduled"),
        "interval_seconds": 60,
        "watch_dir": "",
        "pattern": "*.mp4",
        "enabled": True,
        "last_run": "",
        "status": "idle",
        "last_error": "",
        "created_at": "",
        "seen_paths": [],
    }
    saved = client.put("/api/v1/schedules/watch-one", json=schedule)
    assert saved.status_code == 200, saved.text
    listing = client.get("/api/v1/schedules").json()
    assert listing["schedules"][0]["id"] == "watch-one"
    run = client.post("/api/v1/schedules/watch-one/run")
    assert run.status_code == 200, run.text
    assert run.json()["schedule"]["status"] in {"queued", "failed"}
    deleted = client.delete("/api/v1/schedules/watch-one")
    assert deleted.status_code == 200
    assert client.get("/api/v1/schedules").json()["schedules"] == []


def test_timeline_batch_move(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    response = client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline/batch",
        json={
            "edits": [
                {"clip_id": "v1", "action": "move", "delta_sec": 0.2},
                {"clip_id": "v2", "action": "move", "delta_sec": 0.2},
            ]
        },
    )
    assert response.status_code == 200, response.text
    payload = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    assert payload["video"][0]["start_sec"] == 0.2
    assert payload["video"][1]["start_sec"] == 1.2
    assert payload["revision"] == 2


def test_markers_and_track_state(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    marker = client.post(
        f"/api/v1/jobs/{job.job_id}/timeline/markers",
        json={"time_sec": 1.5, "label": "cut here"},
    )
    assert marker.status_code == 201, marker.text
    assert marker.json()["markers"][0]["label"] == "cut here"
    track = client.put(
        f"/api/v1/jobs/{job.job_id}/timeline/tracks/audio",
        json={"muted": True, "solo": False, "locked": False},
    )
    assert track.status_code == 200, track.text
    payload = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    assert payload["markers"][0]["time_sec"] == 1.5
    assert payload["tracks"]["audio"]["muted"] is True


def test_review_comments_and_thumbnail_metrics(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    output = tmp_path / "out"
    (output / "review.json").write_text('{"checks": [{"id": "timeline", "ok": true}]}')
    thumbs = output / "thumbnails"
    thumbs.mkdir(exist_ok=True)
    (thumbs / "thumbnail-1.png").write_bytes(b"png")
    (thumbs / "thumbnail-2.png").write_bytes(b"png")
    comment = client.post(
        f"/api/v1/jobs/{job.job_id}/review/comments",
        json={"author": "qa", "text": "looks good", "time_sec": 1.0},
    )
    assert comment.status_code == 201, comment.text
    assert comment.json()["comments"][0]["text"] == "looks good"
    metric = client.post(
        f"/api/v1/jobs/{job.job_id}/thumbnails/thumbnail-1.png/metric",
        json={"impressions": 10, "clicks": 2},
    )
    assert metric.status_code == 200, metric.text
    metrics = client.get(f"/api/v1/jobs/{job.job_id}/thumbnails/metrics").json()["metrics"]
    assert metrics[0]["ctr"] == 0.2
    selected = client.post(
        f"/api/v1/jobs/{job.job_id}/thumbnails/select",
        json={"name": "thumbnail-2.png"},
    )
    assert selected.status_code == 200
    listing = client.get(f"/api/v1/jobs/{job.job_id}/thumbnails").json()
    assert listing["selected"] == "thumbnail-2.png"


def test_provider_secret_presence(monkeypatch, tmp_path: Path) -> None:
    client, _ = _client(monkeypatch, tmp_path)
    provider = {
        "id": "secret-llm",
        "name": "Secret LLM",
        "capability": "llm",
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key_env": "VIDEOWFLOW_TEST_PROVIDER_KEY",
        "model": "test",
        "enabled": True,
        "is_default": True,
        "fallback": [],
        "notes": "",
    }
    assert client.put("/api/v1/providers/secret-llm", json=provider).status_code == 200
    stored = client.post(
        "/api/v1/providers/secret-llm/secret", json={"value": "top-secret"}
    )
    assert stored.status_code == 200, stored.text
    listing = client.get("/api/v1/providers").json()
    assert listing["providers"][0]["secret_present"] is True
    assert "top-secret" not in str(listing)
    cleared = client.delete("/api/v1/providers/secret-llm/secret")
    assert cleared.status_code == 200
    listing = client.get("/api/v1/providers").json()
    assert listing["providers"][0]["secret_present"] is False


def test_settings_roundtrip(monkeypatch, tmp_path: Path) -> None:
    client, _ = _client(monkeypatch, tmp_path)
    original = client.get("/api/v1/settings").json()["settings"]
    assert original["runtime"]["max_jobs"] == 2
    original["runtime"]["max_jobs"] = 3
    original["llm"]["temperature"] = 0.4
    saved = client.put("/api/v1/settings", json=original)
    assert saved.status_code == 200, saved.text
    loaded = client.get("/api/v1/settings").json()["settings"]
    assert loaded["runtime"]["max_jobs"] == 3
    assert loaded["llm"]["temperature"] == 0.4
    reset = client.post("/api/v1/settings/reset")
    assert reset.status_code == 200
    assert client.get("/api/v1/settings").json()["settings"]["runtime"]["max_jobs"] == 2


def test_local_model_registration_and_verify(monkeypatch, tmp_path: Path) -> None:
    client, _ = _client(monkeypatch, tmp_path)
    model_path = tmp_path / "custom-model.bin"
    model_path.write_bytes(b"model")
    registered = client.post(
        "/api/v1/models/local",
        json={
            "id": "custom-asr",
            "label": "Custom ASR",
            "capability": "asr",
            "path": str(model_path),
            "kind": "local",
        },
    )
    assert registered.status_code == 201, registered.text
    models = client.get("/api/v1/models").json()["models"]
    assert any(item["id"] == "custom-asr" and item["custom"] for item in models)
    verified = client.post("/api/v1/models/custom-asr/verify")
    assert verified.status_code == 200
    assert verified.json()["verification"]["ok"] is True


def test_service_definition_crud_and_support_bundle(monkeypatch, tmp_path: Path) -> None:
    client, _ = _client(monkeypatch, tmp_path)
    service = {
        "id": "local-test",
        "name": "Local test",
        "command": "/bin/true",
        "args": [],
        "cwd": str(tmp_path),
        "env": {},
        "port": 0,
        "health_url": "",
        "autostart": False,
        "enabled": True,
    }
    saved = client.put("/api/v1/services/definitions/local-test", json=service)
    assert saved.status_code == 200, saved.text
    listing = client.get("/api/v1/services/definitions").json()
    assert listing["services"][0]["id"] == "local-test"
    deleted = client.delete("/api/v1/services/definitions/local-test")
    assert deleted.status_code == 200

    bundle = client.get("/api/v1/system/support-bundle")
    assert bundle.status_code == 200
    assert bundle.headers["content-type"] == "application/zip"
    assert len(bundle.content) > 100


def test_human_gate_resume_route(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    assets = tmp_path / "assets"
    assets.mkdir()
    recipe = {
        "schema_version": 1,
        "id": "gate_api",
        "name": "Gate API",
        "steps": [
            {"id": "index", "type": "assets.index", "params": {"asset_dir": str(assets)}},
            {
                "id": "gate",
                "type": "human.gate",
                "needs": ["index"],
                "params": {"gate_id": "review", "title": "Review"},
            },
        ],
    }
    job = manager.start(
        source, tmp_path / "out", {"mode": "recipe", "recipe": recipe}, queue=True
    )
    for _ in range(300):
        if job.status in {"waiting_approval", "failed", "succeeded"}:
            break
        time.sleep(0.01)
    assert job.status == "waiting_approval", job.error
    response = client.post(
        f"/api/v1/jobs/{job.job_id}/resume",
        json={"approved": True, "comment": "ok"},
    )
    assert response.status_code == 202, response.text
    resumed = manager.get(response.json()["job"]["job_id"])
    for _ in range(300):
        if resumed.status in {"succeeded", "failed"}:
            break
        time.sleep(0.01)
    assert resumed.status == "succeeded", resumed.error


def test_locked_track_blocks_clip_edits(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    locked = client.put(
        f"/api/v1/jobs/{job.job_id}/timeline/tracks/video",
        json={"muted": False, "solo": False, "locked": True},
    )
    assert locked.status_code == 200, locked.text

    response = client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline",
        json={"clip_id": "v1", "action": "move", "delta_sec": 0.5},
    )

    assert response.status_code == 409
    assert "locked" in response.json()["detail"]["message"].lower()


def test_unlocked_track_allows_the_edit_again(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    client.put(
        f"/api/v1/jobs/{job.job_id}/timeline/tracks/video",
        json={"muted": False, "solo": False, "locked": True},
    )
    client.put(
        f"/api/v1/jobs/{job.job_id}/timeline/tracks/video",
        json={"muted": False, "solo": False, "locked": False},
    )

    response = client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline",
        json={"clip_id": "v1", "action": "move", "delta_sec": 0.5},
    )

    assert response.status_code == 200, response.text


def test_clip_comments_crud(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)

    created = client.post(
        f"/api/v1/jobs/{job.job_id}/timeline/comments",
        json={"clip_id": "v1", "text": "tighten this cut", "author": "tester"},
    )
    assert created.status_code == 201, created.text
    [comment] = client.get(
        f"/api/v1/jobs/{job.job_id}/timeline/comments?clip_id=v1"
    ).json()["comments"]
    assert comment["text"] == "tighten this cut"

    removed = client.delete(
        f"/api/v1/jobs/{job.job_id}/timeline/comments/{comment['id']}"
    )
    assert removed.status_code == 200
    assert client.get(
        f"/api/v1/jobs/{job.job_id}/timeline/comments"
    ).json()["comments"] == []


def test_duplicate_route_inserts_a_clip(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)

    response = client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline",
        json={"clip_id": "v1", "action": "duplicate"},
    )

    assert response.status_code == 200, response.text
    timeline = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    assert len(timeline["video"]) == 3


def test_overlay_add_and_delete(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    image = tmp_path / "logo.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")

    created = client.post(
        f"/api/v1/jobs/{job.job_id}/timeline/overlays",
        json={
            "asset_id": "asset-1",
            "path": str(image),
            "start_sec": 0.5,
            "duration_sec": 2.0,
            "width_ratio": 0.3,
        },
    )
    assert created.status_code == 201, created.text
    [overlay] = created.json()["overlays"]
    assert overlay["asset_id"] == "asset-1"

    timeline = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    assert timeline["overlays"][0]["overlay_id"] == overlay["overlay_id"]

    removed = client.delete(
        f"/api/v1/jobs/{job.job_id}/timeline/overlays/{overlay['overlay_id']}"
    )
    assert removed.status_code == 200
    assert removed.json()["overlays"] == []


def test_timeline_etag_and_if_match(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    first = client.get(f"/api/v1/jobs/{job.job_id}/timeline")
    assert first.status_code == 200
    etag = first.headers["etag"]
    assert etag == f'"timeline-{first.json()["revision"]}"'

    cached = client.get(
        f"/api/v1/jobs/{job.job_id}/timeline", headers={"If-None-Match": etag}
    )
    assert cached.status_code == 304

    stale = client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline",
        headers={"If-Match": '"timeline-999"'},
        json={"clip_id": "v1", "action": "split", "split_sec": 0.5},
    )
    assert stale.status_code == 412
    assert stale.json()["detail"]["code"] == "precondition_failed"

    stale_batch = client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline/batch",
        headers={"If-Match": '"timeline-999"'},
        json={"edits": [{"clip_id": "v1", "action": "move", "delta_sec": 0.1}]},
    )
    assert stale_batch.status_code == 412
    assert stale_batch.json()["detail"]["code"] == "precondition_failed"

    applied = client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline",
        headers={"If-Match": etag},
        json={"clip_id": "v1", "action": "split", "split_sec": 0.5},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["etag"] != etag


def test_timeline_deactivate_activate_and_reports_inactive(monkeypatch, tmp_path: Path) -> None:
    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    base = f"/api/v1/jobs/{job.job_id}/timeline"

    deactivated = client.patch(
        base,
        json={"clip_id": "v2", "action": "deactivate"},
    )
    assert deactivated.status_code == 200, deactivated.text
    payload = client.get(base).json()
    assert [clip["id"] for clip in payload["video"]] == ["v1"]
    assert payload["inactive"][0]["id"] == "v2"
    assert payload["inactive"][0]["reason"] == "manual"
    assert payload["source_duration_sec"] > payload["duration_sec"]

    activated = client.patch(
        base,
        json={"clip_id": "v2", "action": "activate"},
    )
    assert activated.status_code == 200, activated.text
    payload = client.get(base).json()
    assert [clip["id"] for clip in payload["video"]] == ["v1", "v2"]
    assert payload["inactive"] == []
