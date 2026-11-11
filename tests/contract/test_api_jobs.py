import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.recipe_jobs import MINIMAL_RECIPE, manager_with_runner, start_recipe
from videoflow.api.app import create_app


def fake_runner(
    source: Path,
    output: Path,
    *,
    progress,
    should_cancel,
    telemetry=None,
    log=None,
    **kwargs,
):
    progress("probe", 5, "probe")
    if telemetry is not None:
        telemetry.start("ingest", "ingest", "Ingest", "probe")
        telemetry.update("ingest", 50, "extract")
        telemetry.finish("ingest", "PCM ready")
    if log is not None:
        log("ingest", "info", "fake PCM")
    output.mkdir(parents=True, exist_ok=True)
    (output / "run.json").write_text("{}", encoding="utf-8")
    (output / "timeline.fcpxml").write_text("<fcpxml/>", encoding="utf-8")
    (output / "project_state.json").write_text(
        '{"transcript":[{"id":0,"start_sample":0,"end_sample":100,'
        '"text":"take one","words":[]},{"id":1,"start_sample":100,'
        '"end_sample":200,"text":"take two","words":[]}],'
        '"retake_culls":[0],"retake_guard_restores":[]}',
        encoding="utf-8",
    )
    return {
        "ok": True,
        "video_segment_count": 1,
        "artifacts": {"resolve": str(output / "timeline.fcpxml")},
    }


def make_client(monkeypatch, tmp_path: Path, runner=fake_runner) -> TestClient:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    manager = manager_with_runner(runner)
    return TestClient(create_app(jobs=manager))


def wait_http(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = client.get(f"/api/v1/jobs/{job_id}").json()["job"]
        if payload["status"] in {"succeeded", "failed", "cancelled"}:
            return payload
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def start_job(
    client: TestClient,
    source: Path,
    output: Path,
    *,
    idempotency_key: str | None = None,
    queue: bool = True,
    priority: int = 0,
    **options,
) -> dict:
    job = client.app.state.jobs.start(
        Path(source),
        Path(output),
        {"mode": "recipe", "recipe": MINIMAL_RECIPE, **options},
        queue=queue,
        priority=priority,
        idempotency_key=idempotency_key,
    )
    return job.to_dict()


def test_create_and_poll_a_job(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    job = start_job(client, source, tmp_path / "out")
    assert wait_http(client, job["job_id"])["status"] == "succeeded"
    assert (tmp_path / "out" / "run.json").is_file()


def test_path_outside_the_allowlist_is_rejected(monkeypatch, tmp_path: Path) -> None:
    client = make_client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/recipes/run",
        json={
            "recipe_id": "youtube_talking_head",
            "source": "/etc/passwd",
            "output": str(tmp_path / "out"),
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "path_not_allowed"


def test_transcript_option_and_state_endpoint(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    job = start_job(client, source, tmp_path / "out")
    wait_http(client, job["job_id"])
    state = client.get(f"/api/v1/jobs/{job['job_id']}/state")
    assert state.status_code == 200
    assert state.json()["retake_culls"] == [0]


def test_state_is_missing_before_a_run(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    start_job(client, source, tmp_path / "out")
    # Fake runner writes state immediately; unknown job is the stable 404 case.
    assert client.get("/api/v1/jobs/missing/state").status_code == 404


def test_artifact_download_is_confined_to_the_job_output(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    job = start_job(client, source, tmp_path / "out")
    wait_http(client, job["job_id"])
    response = client.get(f"/api/v1/jobs/{job['job_id']}/artifacts/resolve")
    assert response.status_code == 200
    assert response.text == "<fcpxml/>"
    assert client.get(f"/api/v1/jobs/{job['job_id']}/artifacts/nope").status_code == 404


def test_job_reports_stages_and_logs(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    job = start_job(client, source, tmp_path / "out")
    finished = wait_http(client, job["job_id"])
    assert finished["stages"][0]["id"] == "ingest"
    assert finished["stages"][0]["duration_ms"] is not None
    assert finished["duration_ms"] is not None
    logs = client.get(f"/api/v1/jobs/{job['job_id']}/logs").json()
    assert logs["total"] == 1
    assert logs["logs"][0]["module"] == "ingest"
    filtered = client.get(f"/api/v1/jobs/{job['job_id']}/logs?module=vad").json()
    assert filtered["logs"] == []
    downloaded = client.get(f"/api/v1/jobs/{job['job_id']}/logs?download=1")
    assert downloaded.status_code == 200
    assert "fake PCM" in downloaded.text




def test_unknown_job_is_404(monkeypatch, tmp_path: Path) -> None:
    client = make_client(monkeypatch, tmp_path)
    assert client.get("/api/v1/jobs/missing").status_code == 404
    assert client.post("/api/v1/jobs/missing/cancel").status_code == 404
    assert client.delete("/api/v1/jobs/missing").status_code == 404


def test_jobs_can_be_force_removed(monkeypatch, tmp_path: Path) -> None:
    import threading

    from videoflow.domain.errors import JobCancelledError

    started = threading.Event()

    def slow(source, output, *, progress, should_cancel, **kwargs):
        started.set()
        while not should_cancel():
            time.sleep(0.01)
        raise JobCancelledError("removed")

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path, runner=slow)
    job = start_job(client, source, tmp_path / "out")
    job_id = job["job_id"]
    assert started.wait(2)

    removed = client.delete(f"/api/v1/jobs/{job_id}?force=true")
    assert removed.status_code == 200, removed.text
    assert removed.json()["removed"] == job_id
    assert client.get(f"/api/v1/jobs/{job_id}").status_code == 404

    terminal_client = make_client(monkeypatch, tmp_path)
    completed = start_job(terminal_client, source, tmp_path / "done")
    done_id = completed["job_id"]
    assert wait_http(terminal_client, done_id)["status"] == "succeeded"
    assert terminal_client.delete(f"/api/v1/jobs/{done_id}").status_code == 200
    assert terminal_client.get(f"/api/v1/jobs/{done_id}").status_code == 404


def test_system_endpoint_reports_roots(monkeypatch, tmp_path: Path) -> None:
    client = make_client(monkeypatch, tmp_path)
    payload = client.get("/api/v1/system").json()
    assert payload["ok"] is True
    assert str(tmp_path) in payload["allowed_roots"]
    assert payload["settings_error"] == ""
    assert payload["database_error"] == ""


def test_events_stream_delivers_the_terminal_state(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    job = start_job(client, source, tmp_path / "out")
    wait_http(client, job["job_id"])
    response = client.get(f"/api/v1/jobs/{job['job_id']}/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"status": "succeeded"' in response.text


@pytest.mark.media


def test_edit_short_updates_result_and_writes_a_new_render(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application.jobs import Job
    from videoflow.domain.state import MediaInfo, ProjectState, Sentence

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    output = tmp_path / "out"
    (output / "shorts").mkdir(parents=True)
    state = ProjectState(
        media_info=MediaInfo(
            source_path=str(source),
            duration_frames=30,
            fps_num=30,
            fps_den=1,
            width=1920,
            height=1080,
            audio_sample_rate=48000,
        ),
        transcript=[Sentence(id=0, start_sample=0, end_sample=48000, text="Hello")],
    )
    (output / "project_state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
    original = output / "shorts" / "01-hello.mp4"
    original.write_bytes(b"old")
    entry = {
        "title": "Hello",
        "pieces": [[0, 48000]],
        "start_sample": 0,
        "end_sample": 48000,
        "start_sec": 0.0,
        "end_sec": 1.0,
        "duration_sec": 1.0,
        "aspect_ratio": "9:16",
        "width": 1080,
        "height": 1920,
        "path": str(original),
    }
    (output / "shorts.json").write_text(
        json.dumps({"ok": True, "clips": [entry]}), encoding="utf-8"
    )
    job = Job(source=source, output=output, options={})
    job.status = "succeeded"
    job.result = {"ok": True, "shorts": [entry]}
    manager = manager_with_runner()
    manager._jobs[str(job.job_id)] = job

    def fake_render(self, source, pieces, destination, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"edited")
        assert kwargs["width"] == 1080
        assert kwargs["height"] == 1080
        return destination

    monkeypatch.setattr(
        "videoflow.adapters.ffmpeg.FFmpegAdapter.render_short", fake_render
    )
    client = TestClient(create_app(jobs=manager))
    response = client.post(
        f"/api/v1/jobs/{job.job_id}/shorts/0/edit",
        json={
            "title": "Edited",
            "start_sec": 0.25,
            "end_sec": 0.75,
            "aspect_ratio": "1:1",
            "caption_style": {"primary_color": "#FF0000"},
        },
    )
    assert response.status_code == 200
    edited = response.json()["short"]
    assert edited["title"] == "Edited"
    assert edited["duration_sec"] == 0.5
    assert edited["aspect_ratio"] == "1:1"
    assert edited["width"] == 1080
    assert edited["height"] == 1080
    assert Path(edited["path"]).is_file()
    assert job.result["shorts"][0]["title"] == "Edited"
    saved = json.loads((output / "shorts.json").read_text(encoding="utf-8"))
    assert saved["clips"][0]["title"] == "Edited"


def test_short_metadata_is_generated_and_persisted(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application.jobs import Job
    from videoflow.domain.state import MediaInfo, ProjectState, Sentence

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    output = tmp_path / "out"
    output.mkdir()
    state = ProjectState(
        media_info=MediaInfo(
            source_path=str(source),
            duration_frames=30,
            fps_num=30,
            fps_den=1,
            width=1920,
            height=1080,
            audio_sample_rate=48000,
        ),
        transcript=[
            Sentence(
                id=0,
                start_sample=0,
                end_sample=48000,
                text="The finance market crashed after the bank decision.",
            )
        ],
    )
    (output / "project_state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
    entry = {
        "title": "Market crash",
        "pieces": [[0, 48000]],
        "start_sample": 0,
        "end_sample": 48000,
        "start_sec": 0.0,
        "end_sec": 1.0,
        "duration_sec": 1.0,
        "path": str(output / "short.mp4"),
    }
    (output / "shorts.json").write_text(
        json.dumps({"ok": True, "clips": [entry]}), encoding="utf-8"
    )
    job = Job(source=source, output=output, options={})
    job.status = "succeeded"
    job.result = {"ok": True, "shorts": [entry]}
    manager = manager_with_runner()
    manager._jobs[str(job.job_id)] = job
    client = TestClient(create_app(jobs=manager))
    response = client.post(
        f"/api/v1/jobs/{job.job_id}/shorts/0/metadata",
        json={"platform": "tiktok", "tone": "bold"},
    )
    assert response.status_code == 200
    metadata = response.json()["metadata"]
    assert metadata["platform"] == "tiktok"
    assert "#fyp" in metadata["hashtags"]
    assert "changes" in metadata["description"]
    saved = json.loads((output / "shorts.json").read_text(encoding="utf-8"))
    assert saved["clips"][0]["metadata"]["tiktok"]["title"] == metadata["title"]


def test_short_thumbnail_is_generated_and_persisted(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application.jobs import Job
    from videoflow.domain.state import MediaInfo, ProjectState, Sentence

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    output = tmp_path / "out"
    (output / "shorts").mkdir(parents=True)
    short_file = output / "shorts" / "short.mp4"
    short_file.write_bytes(b"video")
    state = ProjectState(
        media_info=MediaInfo(
            source_path=str(source),
            duration_frames=30,
            fps_num=30,
            fps_den=1,
            width=1920,
            height=1080,
            audio_sample_rate=48000,
        ),
        transcript=[Sentence(id=0, start_sample=0, end_sample=48000, text="Hello")],
    )
    (output / "project_state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
    entry = {
        "title": "Hello",
        "pieces": [[0, 48000]],
        "start_sample": 0,
        "end_sample": 48000,
        "start_sec": 0.0,
        "end_sec": 1.0,
        "duration_sec": 1.0,
        "aspect_ratio": "9:16",
        "width": 1080,
        "height": 1920,
        "path": str(short_file),
    }
    (output / "shorts.json").write_text(
        json.dumps({"ok": True, "clips": [entry]}), encoding="utf-8"
    )
    job = Job(source=source, output=output, options={})
    job.status = "succeeded"
    job.result = {"ok": True, "shorts": [entry]}
    manager = manager_with_runner()
    manager._jobs[str(job.job_id)] = job

    def fake_thumbnail(self, source, destination, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"png")
        return destination

    monkeypatch.setattr(
        "videoflow.application.thumbnail.FFmpegAdapter.render_thumbnail", fake_thumbnail
    )
    client = TestClient(create_app(jobs=manager))
    response = client.post(
        f"/api/v1/jobs/{job.job_id}/shorts/0/thumbnail",
        json={"time_sec": 0.5, "title": "Thumb"},
    )
    assert response.status_code == 200
    thumbnail = response.json()["thumbnail"]
    assert thumbnail["title"] == "Thumb"
    assert Path(thumbnail["path"]).is_file()
    assert job.result["shorts"][0]["thumbnail"] == thumbnail["path"]
    saved = json.loads((output / "shorts.json").read_text(encoding="utf-8"))
    assert saved["clips"][0]["thumbnails"][0]["title"] == "Thumb"


def test_short_voiceover_mixes_and_persists(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application.jobs import Job
    from videoflow.domain.state import MediaInfo, ProjectState, Sentence

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    output = tmp_path / "out"
    (output / "shorts").mkdir(parents=True)
    short_file = output / "shorts" / "short.mp4"
    short_file.write_bytes(b"video")
    state = ProjectState(
        media_info=MediaInfo(
            source_path=str(source),
            duration_frames=30,
            fps_num=30,
            fps_den=1,
            width=1920,
            height=1080,
            audio_sample_rate=48000,
        ),
        transcript=[Sentence(id=0, start_sample=0, end_sample=48000, text="Hello")],
    )
    (output / "project_state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
    entry = {
        "title": "Hello",
        "pieces": [[0, 48000]],
        "start_sample": 0,
        "end_sample": 48000,
        "start_sec": 0.0,
        "end_sec": 1.0,
        "duration_sec": 1.0,
        "path": str(short_file),
    }
    (output / "shorts.json").write_text(
        json.dumps({"ok": True, "clips": [entry]}), encoding="utf-8"
    )
    job = Job(source=source, output=output, options={})
    job.status = "succeeded"
    job.result = {"ok": True, "shorts": [entry]}
    manager = manager_with_runner()
    manager._jobs[str(job.job_id)] = job

    def fake_tts(self, text, destination, **kwargs):
        destination.write_bytes(b"audio")
        return destination

    def fake_mix(self, short_path, voice_path, destination, **kwargs):
        destination.write_bytes(b"mixed")
        return destination

    monkeypatch.setattr("videoflow.adapters.tts.OpenAITtsAdapter.synthesize", fake_tts)
    monkeypatch.setattr(
        "videoflow.application.voiceover.FFmpegAdapter.mix_voiceover", fake_mix
    )
    client = TestClient(create_app(jobs=manager))
    response = client.post(
        f"/api/v1/jobs/{job.job_id}/shorts/0/voiceover",
        json={
            "text": "Narration",
            "base_url": "http://localhost:8880/v1",
            "allow_external_services": True,
        },
    )
    assert response.status_code == 200
    voiceover = response.json()["voiceover"]
    assert voiceover["text"] == "Narration"
    assert Path(voiceover["path"]).is_file()
    assert job.result["shorts"][0]["voiceover"]["voice"] == "alloy"
    saved = json.loads((output / "shorts.json").read_text(encoding="utf-8"))
    assert saved["clips"][0]["voiceover"]["text"] == "Narration"


def test_short_dubbing_translates_and_mixes(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application.jobs import Job
    from videoflow.domain.state import MediaInfo, ProjectState, Sentence

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    output = tmp_path / "out"
    (output / "shorts").mkdir(parents=True)
    short_file = output / "shorts" / "short.mp4"
    short_file.write_bytes(b"video")
    state = ProjectState(
        media_info=MediaInfo(
            source_path=str(source),
            duration_frames=30,
            fps_num=30,
            fps_den=1,
            width=1920,
            height=1080,
            audio_sample_rate=48000,
        ),
        transcript=[Sentence(id=0, start_sample=0, end_sample=48000, text="Hello")],
    )
    (output / "project_state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
    entry = {
        "title": "Hello",
        "pieces": [[0, 48000]],
        "start_sample": 0,
        "end_sample": 48000,
        "start_sec": 0.0,
        "end_sec": 1.0,
        "duration_sec": 1.0,
        "path": str(short_file),
    }
    (output / "shorts.json").write_text(
        json.dumps({"ok": True, "clips": [entry]}), encoding="utf-8"
    )
    job = Job(source=source, output=output, options={})
    job.status = "succeeded"
    job.result = {"ok": True, "shorts": [entry]}
    manager = manager_with_runner()
    manager._jobs[str(job.job_id)] = job

    def fake_llm(self, prompt, schema_name):
        return {"text": "Olá"}

    def fake_tts(self, text, destination, **kwargs):
        destination.write_bytes(b"audio")
        return destination

    def fake_mix(self, short_path, voice_path, destination, **kwargs):
        destination.write_bytes(b"mixed")
        return destination

    monkeypatch.setattr(
        "videoflow.application.dubbing.OpenAICompatibleLlm.complete_json", fake_llm
    )
    monkeypatch.setattr(
        "videoflow.application.dubbing.OpenAITtsAdapter.synthesize", fake_tts
    )
    monkeypatch.setattr(
        "videoflow.application.dubbing.FFmpegAdapter.mix_voiceover", fake_mix
    )
    client = TestClient(create_app(jobs=manager))
    response = client.post(
        f"/api/v1/jobs/{job.job_id}/shorts/0/dub",
        json={
            "target_language": "pt",
            "base_url": "http://localhost:8880/v1",
            "llm_base_url": "http://localhost:11434/v1",
            "allow_external_services": True,
        },
    )
    assert response.status_code == 200
    dubbing = response.json()["dubbing"]
    assert dubbing["translated_text"] == "Olá"
    assert dubbing["target_language"] == "pt"
    assert Path(dubbing["path"]).is_file()
    saved = json.loads((output / "shorts.json").read_text(encoding="utf-8"))
    assert saved["clips"][0]["dubbing"]["translated_text"] == "Olá"


def test_job_artifact_and_short_file_routes(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from tests.recipe_jobs import manager_with_runner
    from videoflow.api.app import create_app

    def runner(source, output, **kwargs):
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        artifact = output / "timeline.mp4"
        artifact.write_bytes(b"mp4")
        short = output / "short.mp4"
        short.write_bytes(b"short")
        return {
            "ok": True,
            "artifacts": {"mp4": str(artifact)},
            "shorts": [{"title": "Short", "path": str(short)}],
            "elapsed_seconds": 0.0,
        }

    manager = manager_with_runner(runner=runner)
    job = start_recipe(manager, tmp_path / "source.mp4", tmp_path / "out", {})
    for _ in range(200):
        if job.status in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.01)
    assert job.status == "succeeded"
    client = TestClient(create_app(jobs=manager))
    artifact = client.get(f"/api/v1/jobs/{job.job_id}/artifacts/mp4")
    assert artifact.status_code == 200
    assert artifact.content == b"mp4"
    short = client.get(f"/api/v1/jobs/{job.job_id}/shorts/0/file")
    assert short.status_code == 200
    assert short.content == b"short"


def test_preview_proxy_routes(monkeypatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from tests.recipe_jobs import manager_with_runner
    from videoflow.api import routes_outputs
    from videoflow.api.app import create_app

    def runner(source, output, **kwargs):
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        artifact = output / "timeline.mp4"
        artifact.write_bytes(b"mp4")
        return {"ok": True, "artifacts": {"mp4": str(artifact)}, "shorts": []}

    monkeypatch.setattr(
        routes_outputs.FFmpegAdapter,
        "transcode_preview",
        lambda self, source, target, **kwargs: target.write_bytes(b"proxy") or target,
    )
    manager = manager_with_runner(runner=runner)
    job = start_recipe(manager, tmp_path / "source.mp4", tmp_path / "out", {})
    for _ in range(200):
        if job.status in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.01)
    client = TestClient(create_app(jobs=manager))
    created = client.post(f"/api/v1/jobs/{job.job_id}/preview")
    assert created.status_code == 200, created.text
    assert created.json()["url"].endswith("/preview/file")
    served = client.get(f"/api/v1/jobs/{job.job_id}/preview/file")
    assert served.status_code == 200
    assert served.content == b"proxy"


def test_timeline_route_from_project_state(monkeypatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from tests.recipe_jobs import manager_with_runner
    from videoflow.api.app import create_app
    from videoflow.domain.state import (
        AudioSegment,
        MediaInfo,
        ProjectState,
        Sentence,
        VideoSegment,
    )

    def runner(source, output, **kwargs):
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        state = ProjectState(
            media_info=MediaInfo(
                source_path=str(source),
                duration_frames=50,
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
                )
            ],
            audio_segments=[
                AudioSegment(
                    clip_id="a1",
                    source_in_sample=0,
                    source_out_sample=48000,
                    timeline_in_sample=0,
                    timeline_out_sample=48000,
                )
            ],
            transcript=[Sentence(id=0, start_sample=0, end_sample=48000, text="old")],
        )
        path = output / "project_state.json"
        path.write_text(state.model_dump_json())
        return {"ok": True, "state_path": str(path), "artifacts": {}, "shorts": []}

    manager = manager_with_runner(runner=runner)
    job = start_recipe(manager, tmp_path / "source.mp4", tmp_path / "out", {})
    for _ in range(200):
        if job.status in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.01)
    client = TestClient(create_app(jobs=manager))
    response = client.get(f"/api/v1/jobs/{job.job_id}/timeline")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["duration_sec"] == 1.0
    assert payload["video"][0]["id"] == "v1"
    assert payload["audio"][0]["id"] == "a1"
    patched = client.patch(
        f"/api/v1/jobs/{job.job_id}/captions/0", json={"text": "new caption"}
    )
    assert patched.status_code == 200, patched.text
    timeline = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    assert timeline["captions"][0]["text"] == "new caption"
    edited = client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline",
        json={"clip_id": "v1", "action": "trim", "start_sec": 0.0, "end_sec": 0.5},
    )
    assert edited.status_code == 200, edited.text
    timeline = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    assert timeline["video"][0]["end_sec"] == 0.48
    deleted = client.patch(
        f"/api/v1/jobs/{job.job_id}/timeline",
        json={"clip_id": "v1", "action": "delete"},
    )
    assert deleted.status_code == 200, deleted.text
    assert client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()["video"] == []


def test_system_doctor_reports_checks() -> None:
    from fastapi.testclient import TestClient

    from videoflow.api.app import create_app

    client = TestClient(create_app())
    response = client.get("/api/v1/system/doctor")
    assert response.status_code == 200
    payload = response.json()
    assert payload["checks"]["version"]
    assert "ffmpeg" in payload["checks"]
    assert "disk" in payload["checks"]


def test_provider_connection_test(monkeypatch) -> None:
    import httpx
    from fastapi.testclient import TestClient

    from videoflow.api import routes_providers
    from videoflow.api.app import create_app

    monkeypatch.setenv("TEST_PROVIDER_KEY", "secret")
    monkeypatch.setattr(
        routes_providers.httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200, text='{"data":[]}', request=httpx.Request("GET", str(args[0]))
        ),
    )
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/providers/test",
        json={
            "base_url": "http://127.0.0.1:11434/v1",
            "api_key_env": "TEST_PROVIDER_KEY",
            "path": "/models",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["secret_present"] is True


def test_job_list_can_omit_the_embedded_recipe(monkeypatch, tmp_path: Path) -> None:
    from tests.contract.test_api_timeline import _client, _job

    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    job.options["recipe"] = {
        "schema_version": 1,
        "id": "large",
        "name": "Large",
        "steps": [{"id": "ingest", "type": "ingest"}],
    }
    job.options["mode"] = "recipe"

    summary = client.get("/api/v1/jobs", params={"summary": True}).json()["jobs"][0]
    full = client.get("/api/v1/jobs").json()["jobs"][0]

    assert "recipe" not in summary["options"]
    assert summary["options"]["mode"] == "recipe"
    assert full["options"]["recipe"]["id"] == "large"


def test_system_reports_an_invalid_settings_file(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application.settings import settings_path

    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json", encoding="utf-8")
    client = make_client(monkeypatch, tmp_path)

    payload = client.get("/api/v1/system").json()
    assert "invalid" in payload["settings_error"]
    doctor = client.get("/api/v1/system/doctor").json()
    assert doctor["checks"]["settings"]["valid"] is False


def test_provider_chat_test_posts_a_completion(monkeypatch) -> None:
    import httpx

    from videoflow.api import routes_providers as routes_module

    calls: list[dict[str, object]] = []

    def fake_post(*args, **kwargs):
        calls.append({"url": str(args[0]), **kwargs})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
            request=httpx.Request("POST", str(args[0])),
        )

    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setattr(routes_module.httpx, "post", fake_post)
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/providers/test",
        json={
            "base_url": "https://api.deepseek.com/v1",
            "api_key_env": "DEEPSEEK_API_KEY",
            "model": "deepseek-chat",
            "mode": "chat",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["mode"] == "chat"
    assert payload["message"] == "OK"
    assert payload["secret_present"] is True
    assert "latency_ms" in payload
    assert calls and calls[0]["url"].endswith("/chat/completions")


def test_provider_test_missing_secret_is_actionable(monkeypatch) -> None:
    import httpx

    from videoflow.api import routes_providers as routes_module

    monkeypatch.delenv("VIDEOWFLOW_TEST_MISSING_KEY", raising=False)
    monkeypatch.setattr(
        routes_module.httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            401,
            json={
                "error": {
                    "message": "Authentication Fails (governor)",
                    "type": "authentication_error",
                }
            },
            request=httpx.Request("GET", str(args[0])),
        ),
    )
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/providers/test",
        json={
            "base_url": "https://api.deepseek.com/v1",
            "api_key_env": "VIDEOWFLOW_TEST_MISSING_KEY",
            "mode": "models",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is False
    assert payload["code"] == "secret_missing"
    assert payload["secret_source"] == "missing"
    assert payload["secret_present"] is False
    assert "No API key was found" in payload["message"]
    assert "VIDEOWFLOW_TEST_MISSING_KEY" in payload["message"]
    assert payload["provider_message"] == "Authentication Fails (governor)"
    assert payload["endpoint"].endswith("/models")


def test_provider_test_uses_the_pasted_secret_without_saving_it(monkeypatch) -> None:
    import httpx

    from videoflow.api import routes_providers as routes_module

    calls: list[dict[str, object]] = []

    def fake_post(*args, **kwargs):
        calls.append({"url": str(args[0]), **kwargs})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "OK"}}]},
            request=httpx.Request("POST", str(args[0])),
        )

    monkeypatch.delenv("VIDEOWFLOW_TEST_FORM_KEY", raising=False)
    monkeypatch.setattr(routes_module.httpx, "post", fake_post)
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/providers/test",
        json={
            "base_url": "https://api.deepseek.com/v1",
            "api_key_env": "VIDEOWFLOW_TEST_FORM_KEY",
            "secret_value": "sk-from-form",
            "model": "deepseek-chat",
            "mode": "chat",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"] == "OK"
    assert payload["secret_source"] == "request"
    assert payload["secret_present"] is True
    assert "Save the provider" in payload["hint"]
    assert calls and calls[0]["headers"]["Authorization"] == "Bearer sk-from-form"


def test_provider_test_rejects_a_bad_key_with_a_clear_message(monkeypatch) -> None:
    import httpx

    from videoflow.api import routes_providers as routes_module

    monkeypatch.setenv("VIDEOWFLOW_TEST_BAD_KEY", "sk-wrong")
    monkeypatch.setattr(
        routes_module.httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            401,
            text='{"error":{"message":"Authentication Fails (governor)"}}',
            request=httpx.Request("GET", str(args[0])),
        ),
    )
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/providers/test",
        json={
            "base_url": "https://api.deepseek.com/v1",
            "api_key_env": "VIDEOWFLOW_TEST_BAD_KEY",
            "mode": "models",
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["code"] == "auth_failed"
    assert payload["secret_source"] == "environment"
    assert "rejected the API key" in payload["message"]
    assert "valid" in payload["hint"]
    assert payload["provider_message"] == "Authentication Fails (governor)"


@pytest.mark.parametrize(
    ("status", "code", "message_part"),
    [
        (404, "endpoint_not_found", "not found"),
        (429, "rate_limited", "rate-limited"),
        (500, "provider_error", "server error"),
    ],
)
def test_provider_test_maps_http_failures(
    monkeypatch, status: int, code: str, message_part: str
) -> None:
    import httpx

    from videoflow.api import routes_providers as routes_module

    monkeypatch.setenv("VIDEOWFLOW_TEST_MAP_KEY", "sk-present")
    monkeypatch.setattr(
        routes_module.httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            status,
            text='{"error":{"message":"raw provider detail"}}',
            request=httpx.Request("GET", str(args[0])),
        ),
    )
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/providers/test",
        json={
            "base_url": "https://api.deepseek.com/v1",
            "api_key_env": "VIDEOWFLOW_TEST_MAP_KEY",
            "mode": "models",
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["code"] == code
    assert message_part in payload["message"]
    assert payload["hint"]
    assert payload["provider_message"] == "raw provider detail"


def test_provider_test_uses_the_saved_provider_secret(monkeypatch) -> None:
    import httpx

    from videoflow.api import routes_providers as routes_module

    calls: list[dict[str, object]] = []

    def fake_post(*args, **kwargs):
        calls.append({"url": str(args[0]), **kwargs})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "OK"}}]},
            request=httpx.Request("POST", str(args[0])),
        )

    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setattr(
        routes_module,
        "list_providers",
        lambda: [
            {
                "id": "deepseek",
                "base_url": "https://api.deepseek.com/v1",
                "api_key_env": "DEEPSEEK_API_KEY",
                "model": "deepseek-chat",
            }
        ],
    )
    monkeypatch.setattr(routes_module.httpx, "post", fake_post)
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/providers/test",
        json={"provider_id": "deepseek", "mode": "chat"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["secret_present"] is True
    assert calls
    assert calls[0]["headers"]["Authorization"] == "Bearer secret"
