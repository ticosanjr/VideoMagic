import threading
import time
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from videoflow.api import routes
from videoflow.api.app import create_app
from videoflow.application.jobs import JobManager
from videoflow.application.projects import ProjectStore
from videoflow.domain.config import ModuleEnabled, ModulesConfig
from videoflow.domain.errors import JobCancelledError
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    SampleSpan,
    Sentence,
    VideoSegment,
    WordTiming,
)

CAPTURED: list[dict[str, object]] = []


def media_info(source: Path) -> MediaInfo:
    return MediaInfo(
        source_path=str(source),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )


def project_runner(
    source: Path,
    output: Path,
    *,
    project_id=None,
    revision=1,
    modules_config=None,
    module_enabled=None,
    transcript_sentences=None,
    **kwargs,
):
    CAPTURED.append(
        {
            "project_id": str(project_id) if project_id else None,
            "revision": revision,
            "modules_config": modules_config,
            "module_enabled": module_enabled,
            "transcript_sentences": transcript_sentences,
        }
    )
    output.mkdir(parents=True, exist_ok=True)
    state = ProjectState(
        project_id=project_id or uuid4(),
        revision=revision,
        media_info=media_info(source),
        modules_config=modules_config or ModulesConfig(),
        module_enabled=module_enabled or ModuleEnabled(),
        transcript=list(transcript_sentences or []),
    )
    (output / "project_state.json").write_text(
        state.model_dump_json(indent=2), encoding="utf-8"
    )
    (output / "run.json").write_text("{}", encoding="utf-8")
    return {"ok": True, "state_revision": revision}


def make_client(
    monkeypatch, tmp_path: Path, runner=project_runner
) -> tuple[TestClient, ProjectStore]:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    store = ProjectStore()
    client = TestClient(create_app(jobs=JobManager(runner), projects=store))
    return client, store


def create_project(client: TestClient, root: Path) -> str:
    response = client.post("/api/v1/projects", json={"root": str(root)})
    assert response.status_code == 201, response.text
    return str(response.json()["project"]["project_id"])


def register_media(
    client: TestClient, monkeypatch, tmp_path: Path, project_id: str
) -> Path:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(routes, "probe_media", lambda path: media_info(source))
    response = client.post(
        f"/api/v1/projects/{project_id}/media", json={"file_path": str(source)}
    )
    assert response.status_code == 200, response.text
    return source


def wait_job(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = client.get(f"/api/v1/jobs/{job_id}").json()["job"]
        if payload["status"] in {"succeeded", "failed", "cancelled"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_create_read_and_list_projects(monkeypatch, tmp_path: Path) -> None:
    client, store = make_client(monkeypatch, tmp_path)
    root = tmp_path / "project"
    response = client.post("/api/v1/projects", json={"root": str(root)})
    assert response.status_code == 201
    payload = response.json()
    project_id = payload["project"]["project_id"]
    assert payload["state"]["project_id"] == project_id
    assert payload["state"]["revision"] == 1
    assert (root / ".videoflow" / "project_state.json").is_file()
    assert (root / ".videoflow" / "revisions" / "000001.json").is_file()

    again = client.post("/api/v1/projects", json={"root": str(root)})
    assert again.status_code == 201
    assert again.json()["project"]["project_id"] == project_id

    listed = client.get("/api/v1/projects").json()
    assert [item["project_id"] for item in listed["projects"]] == [project_id]
    state = client.get(f"/api/v1/projects/{project_id}/state").json()
    assert state["revision"] == 1
    assert store.get(project_id).revision == 1


def test_project_create_can_apply_a_shipped_preset(monkeypatch, tmp_path: Path) -> None:
    client, _store = make_client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/projects",
        json={"root": str(tmp_path / "preset-project"), "preset": "youtube-talking-head"},
    )
    assert response.status_code == 201, response.text
    state = response.json()["state"]
    assert state["module_enabled"]["shorts"] is False
    assert state["modules_config"]["zooms"]["punch_in_scale"] == 1.15


def test_media_registration_is_jailed_and_invalidates_results(
    monkeypatch, tmp_path: Path
) -> None:
    client, store = make_client(monkeypatch, tmp_path)
    project_id = create_project(client, tmp_path / "project")
    source = register_media(client, monkeypatch, tmp_path, project_id)
    state = client.get(f"/api/v1/projects/{project_id}/state").json()
    assert state["media_info"]["source_path"] == str(source)
    assert state["revision"] == 2
    assert store.get(project_id).revision == 2

    outside = client.post(
        f"/api/v1/projects/{project_id}/media", json={"file_path": "/etc/passwd"}
    )
    assert outside.status_code == 403
    assert outside.json()["detail"]["code"] == "path_not_allowed"

    missing = tmp_path / "missing.mp4"
    bad = client.post(
        f"/api/v1/projects/{project_id}/media", json={"file_path": str(missing)}
    )
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "media_not_found"


def test_module_config_and_enabled_flags_persist(monkeypatch, tmp_path: Path) -> None:
    client, store = make_client(monkeypatch, tmp_path)
    project_id = create_project(client, tmp_path / "project")
    config = client.put(
        f"/api/v1/projects/{project_id}/modules/zooms/config",
        json={"punch_in_scale": 1.25},
    )
    assert config.status_code == 200, config.text
    assert config.json()["config"]["punch_in_scale"] == 1.25
    assert config.json()["config"]["mode"] == "alternate_cuts"
    assert config.json()["state"]["revision"] == 2

    enabled = client.put(
        f"/api/v1/projects/{project_id}/modules/zooms/enabled",
        json={"enabled": False},
    )
    assert enabled.status_code == 200
    assert enabled.json()["state"]["module_enabled"]["zooms"] is False
    assert store.read_state(project_id).module_enabled.zooms is False

    invalid = client.put(
        f"/api/v1/projects/{project_id}/modules/zooms/config",
        json={"punch_in_scale": 2.0},
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_config"

    unknown = client.put(
        f"/api/v1/projects/{project_id}/modules/color/config", json={}
    )
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["code"] == "unknown_module"

    register_media(client, monkeypatch, tmp_path, project_id)
    client.put(
        f"/api/v1/projects/{project_id}/modules/zooms/enabled",
        json={"enabled": True},
    )
    module_run = client.post(f"/api/v1/projects/{project_id}/modules/zooms/run")
    assert module_run.status_code == 202, module_run.text
    payload = module_run.json()
    assert payload["mode"] == "full_pipeline"
    assert "zooms" in payload["planned"]
    assert payload["job"] is not None
    wait_job(client, payload["job"]["job_id"])


def test_transcript_read_and_atomic_overrides(monkeypatch, tmp_path: Path) -> None:
    client, store = make_client(monkeypatch, tmp_path)
    project_id = create_project(client, tmp_path / "project")
    register_media(client, monkeypatch, tmp_path, project_id)
    state = store.read_state(project_id)
    words = [WordTiming(word="hello", start_sample=0, end_sample=500, probability=0.9)]
    state = state.model_copy(
        update={
            "transcript": [
                Sentence(
                    id=0,
                    start_sample=0,
                    end_sample=48000,
                    text="hello",
                    words=words,
                )
            ],
            "retake_culls": [0],
            "video_segments": [
                VideoSegment(
                    clip_id="c1",
                    source_in_frame=0,
                    source_out_frame=30,
                    timeline_in_frame=0,
                    timeline_out_frame=30,
                )
            ],
            "audio_segments": [
                AudioSegment(
                    clip_id="c1",
                    source_in_sample=0,
                    source_out_sample=48000,
                    timeline_in_sample=0,
                    timeline_out_sample=48000,
                )
            ],
        }
    )
    state, _record = store.save_state(project_id, state)
    revision = state.revision

    transcript = client.get(
        f"/api/v1/projects/{project_id}/transcript"
    ).json()
    assert transcript["sentence_count"] == 1
    assert transcript["transcript"][0]["words"][0]["word"] == "hello"
    assert "00:00:00,000 --> 00:00:01,000" in transcript["srt"]

    plain = client.get(
        f"/api/v1/projects/{project_id}/transcript?include_word_timestamps=false"
    ).json()
    assert "words" not in plain["transcript"][0]

    updated = client.patch(
        f"/api/v1/projects/{project_id}/transcript/overrides",
        json={"overrides": [{"sentence_id": 0, "action": "discard"}]},
    )
    assert updated.status_code == 200, updated.text
    payload = updated.json()["state"]
    assert payload["revision"] == revision + 1
    assert payload["manual_overrides"] == [
        {"sentence_id": 0, "word_index": None, "action": "discard"}
    ]
    assert payload["retake_culls"] == []
    assert payload["video_segments"] == []

    invalid = client.patch(
        f"/api/v1/projects/{project_id}/transcript/overrides",
        json={"overrides": [{"sentence_id": 99, "action": "discard"}]},
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_override"

    word = client.patch(
        f"/api/v1/projects/{project_id}/transcript/overrides",
        json={
            "overrides": [
                {"sentence_id": 0, "word_index": 0, "action": "discard"}
            ]
        },
    )
    assert word.status_code == 422
    assert word.json()["detail"]["code"] == "word_overrides_not_supported"


def test_project_exports_and_missing_timeline(monkeypatch, tmp_path: Path) -> None:
    client, store = make_client(monkeypatch, tmp_path)
    project_id = create_project(client, tmp_path / "project")
    source = register_media(client, monkeypatch, tmp_path, project_id)
    missing = client.post(f"/api/v1/projects/{project_id}/exports", json={})
    assert missing.status_code == 409
    assert missing.json()["detail"]["code"] == "state_not_ready"

    state = store.read_state(project_id)
    state = state.model_copy(
        update={
            "video_segments": [
                VideoSegment(
                    clip_id="c1",
                    source_in_frame=0,
                    source_out_frame=30,
                    timeline_in_frame=0,
                    timeline_out_frame=30,
                )
            ],
            "audio_segments": [
                AudioSegment(
                    clip_id="c1",
                    source_in_sample=0,
                    source_out_sample=48000,
                    timeline_in_sample=0,
                    timeline_out_sample=48000,
                )
            ],
        }
    )
    store.save_state(project_id, state)
    response = client.post(f"/api/v1/projects/{project_id}/exports", json={})
    assert response.status_code == 200, response.text
    artifacts = response.json()["artifacts"]
    assert set(artifacts) == {"resolve", "premiere", "kdenlive"}
    assert all(Path(path).is_file() for path in artifacts.values())
    assert artifacts["resolve"].startswith(str(source.parent))

    single = client.post(
        f"/api/v1/projects/{project_id}/exports",
        json={"targets": ["resolve"], "dialect": "1.10"},
    )
    assert single.status_code == 200
    assert set(single.json()["artifacts"]) == {"resolve"}
    assert 'version="1.10"' in Path(single.json()["artifacts"]["resolve"]).read_text(
        encoding="utf-8"
    )


def test_presets_can_be_listed_read_written_and_applied(monkeypatch, tmp_path: Path) -> None:
    client, _store = make_client(monkeypatch, tmp_path)
    listed = client.get("/api/v1/presets")
    assert listed.status_code == 200
    names = {item["name"] for item in listed.json()["presets"]}
    assert {"lecture-clean", "shorts-aggressive", "youtube-talking-head"} <= names

    shipped = client.get("/api/v1/presets/youtube-talking-head")
    assert shipped.status_code == 200
    assert shipped.json()["preset"]["source"] == "shipped"

    written = client.put(
        "/api/v1/presets/operator-test",
        json={
            "description": "Operator test preset.",
            "modules_config": {"zooms": {"punch_in_scale": 1.25}},
            "module_enabled": {"shorts": False},
        },
    )
    assert written.status_code == 200, written.text
    preset = written.json()["preset"]
    assert preset["source"] == "operator"
    assert preset["modules_config"]["zooms"]["punch_in_scale"] == 1.25
    assert (tmp_path / "home" / "presets" / "operator-test.json").is_file()
    assert client.get("/api/v1/presets/operator-test").json()["preset"]["name"] == (
        "operator-test"
    )

    project_id = create_project(client, tmp_path / "project")
    applied = client.post(
        f"/api/v1/projects/{project_id}/presets/operator-test/apply"
    )
    assert applied.status_code == 200
    state = applied.json()["state"]
    assert state["modules_config"]["zooms"]["punch_in_scale"] == 1.25
    assert state["module_enabled"]["shorts"] is False

    assert client.get("/api/v1/presets/missing").status_code == 404
    assert client.put("/api/v1/presets/Bad Name", json={}).status_code == 422
    invalid = client.put(
        "/api/v1/presets/bad-config",
        json={"description": "bad", "modules_config": {"zooms": {"punch_in_scale": 2}}},
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "preset_invalid"


def test_project_run_carries_config_transcript_and_revision(
    monkeypatch, tmp_path: Path
) -> None:
    client, store = make_client(monkeypatch, tmp_path)
    project_id = create_project(client, tmp_path / "project")
    source = register_media(client, monkeypatch, tmp_path, project_id)
    client.put(
        f"/api/v1/projects/{project_id}/modules/zooms/config",
        json={"punch_in_scale": 1.25},
    )
    state = store.read_state(project_id)
    state = state.model_copy(
        update={
            "transcript": [
                Sentence(id=0, start_sample=0, end_sample=1000, text="hello")
            ]
        }
    )
    state, record = store.save_state(project_id, state)
    CAPTURED.clear()

    response = client.post(f"/api/v1/projects/{project_id}/run", json={})
    assert response.status_code == 202, response.text
    job = response.json()["job"]
    assert job["options"]["project_id"] == project_id
    finished = wait_job(client, job["job_id"])
    assert finished["status"] == "succeeded", finished
    assert finished["result"]["state_revision"] == record.revision + 1

    captured = CAPTURED[-1]
    assert captured["project_id"] == project_id
    assert captured["revision"] == record.revision + 1
    assert captured["modules_config"].zooms.punch_in_scale == 1.25
    assert captured["module_enabled"].ingest is True
    assert [item.text for item in captured["transcript_sentences"]] == ["hello"]

    final_state = client.get(f"/api/v1/projects/{project_id}/state").json()
    assert final_state["revision"] == record.revision + 1
    assert final_state["modules_config"]["zooms"]["punch_in_scale"] == 1.25
    assert final_state["transcript"][0]["text"] == "hello"
    revisions = tmp_path / "project" / ".videoflow" / "revisions"
    snapshots = {path.name for path in revisions.iterdir()}
    assert f"{record.revision + 1:06d}.json" in snapshots
    assert source.is_file()

    events = client.get(f"/api/v1/projects/{project_id}/events")
    assert events.status_code == 200
    assert '"status": "succeeded"' in events.text


def test_project_run_requires_media_and_enabled_ingest(
    monkeypatch, tmp_path: Path
) -> None:
    client, _store = make_client(monkeypatch, tmp_path)
    project_id = create_project(client, tmp_path / "project")
    no_media = client.post(f"/api/v1/projects/{project_id}/run", json={})
    assert no_media.status_code == 409
    assert no_media.json()["detail"]["code"] == "media_not_registered"

    register_media(client, monkeypatch, tmp_path, project_id)
    disabled = client.put(
        f"/api/v1/projects/{project_id}/modules/ingest/enabled",
        json={"enabled": False},
    )
    assert disabled.status_code == 200
    blocked = client.post(f"/api/v1/projects/{project_id}/run", json={})
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "module_bypassed"


def test_project_run_rejects_shorts_without_a_transcript(
    monkeypatch, tmp_path: Path
) -> None:
    client, _store = make_client(monkeypatch, tmp_path)
    project_id = create_project(client, tmp_path / "project")
    register_media(client, monkeypatch, tmp_path, project_id)
    client.put(
        f"/api/v1/projects/{project_id}/modules/transcribe/enabled",
        json={"enabled": False},
    )
    response = client.post(f"/api/v1/projects/{project_id}/run", json={})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "transcript_required"


def test_project_job_can_be_cancelled(monkeypatch, tmp_path: Path) -> None:
    started = threading.Event()

    def runner(source: Path, output: Path, *, should_cancel, **kwargs):
        started.set()
        while not should_cancel():
            time.sleep(0.01)
        raise JobCancelledError("cancelled by test")

    client, _store = make_client(monkeypatch, tmp_path, runner=runner)
    project_id = create_project(client, tmp_path / "project")
    register_media(client, monkeypatch, tmp_path, project_id)
    response = client.post(f"/api/v1/projects/{project_id}/run", json={})
    assert response.status_code == 202
    assert started.wait(2)
    cancelled = client.post(f"/api/v1/projects/{project_id}/cancel")
    assert cancelled.status_code == 200
    assert wait_job(client, response.json()["job"]["job_id"])["status"] == "cancelled"
    assert client.post(f"/api/v1/projects/{project_id}/cancel").status_code == 404


def test_unknown_project_returns_typed_404(monkeypatch, tmp_path: Path) -> None:
    client, _store = make_client(monkeypatch, tmp_path)
    missing = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/api/v1/projects/{missing}/state")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "project_not_found"
    assert client.get(f"/api/v1/projects/{missing}/events").status_code == 404


def test_module_run_is_a_noop_when_target_is_cached(monkeypatch, tmp_path: Path) -> None:
    client, store = make_client(monkeypatch, tmp_path)
    project_id = create_project(client, tmp_path / "project")
    register_media(client, monkeypatch, tmp_path, project_id)
    state = store.read_state(project_id)
    state = state.model_copy(
        update={
            "vad_intervals": [SampleSpan(start_sample=0, end_sample=48000)],
            "transcript": [Sentence(id=0, start_sample=0, end_sample=48000, text="hi")],
            "video_segments": [
                VideoSegment(
                    clip_id="c1",
                    source_in_frame=0,
                    source_out_frame=30,
                    timeline_in_frame=0,
                    timeline_out_frame=30,
                )
            ],
            "audio_segments": [
                AudioSegment(
                    clip_id="c1",
                    source_in_sample=0,
                    source_out_sample=48000,
                    timeline_in_sample=0,
                    timeline_out_sample=48000,
                )
            ],
        }
    )
    state, record = store.save_state(project_id, state)
    (record.videoflow_dir / "exports").mkdir(parents=True, exist_ok=True)
    (record.videoflow_dir / "exports" / "timeline.fcpxml").write_text("x")
    (record.videoflow_dir / "shorts.json").write_text("{}")
    response = client.post(f"/api/v1/projects/{project_id}/modules/export/run")
    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["mode"] == "cached"
    assert payload["job"] is None
    assert payload["planned"] == []


def test_export_validation_route(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application.timeline_builder import build_timeline
    from videoflow.domain.config import JlCutsConfig, ZoomsConfig
    from videoflow.exporters.fcpxml import export_fcpxml
    from videoflow.exporters.kdenlive import export_kdenlive
    from videoflow.exporters.xmeml import export_xmeml

    client, _store = make_client(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    media = media_info(source)
    built = build_timeline(
        media,
        [(0, 24000), (48000, 72000)],
        jl=JlCutsConfig(enable_j_cuts=False),
        zooms=ZoomsConfig(mode="manual_rules"),
        transition_frames=4,
    )
    state = ProjectState(
        media_info=media,
        video_segments=list(built.video_segments),
        audio_segments=list(built.audio_segments),
    )
    exports = tmp_path / "out" / "exports"
    exports.mkdir(parents=True)
    export_fcpxml(state, exports / "timeline.fcpxml")
    export_xmeml(state, exports / "timeline.xml")
    export_kdenlive(state, exports / "timeline.kdenlive")
    response = client.post(
        "/api/v1/exports/validate", json={"output": str(tmp_path / "out")}
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
