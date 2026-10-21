import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videoflow.api.app import create_app
from videoflow.application.jobs import JobManager


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
    manager = JobManager(runner)
    return TestClient(create_app(jobs=manager))


def wait_http(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = client.get(f"/api/v1/jobs/{job_id}").json()["job"]
        if payload["status"] in {"succeeded", "failed", "cancelled"}:
            return payload
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_create_and_poll_a_job(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/jobs",
        json={"source": str(source), "output": str(tmp_path / "out")},
    )
    assert response.status_code == 202
    job = response.json()["job"]
    assert wait_http(client, job["job_id"])["status"] == "succeeded"
    assert (tmp_path / "out" / "run.json").is_file()


def test_path_outside_the_allowlist_is_rejected(monkeypatch, tmp_path: Path) -> None:
    client = make_client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/jobs",
        json={"source": "/etc/passwd", "output": str(tmp_path / "out")},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "path_not_allowed"


def test_transcript_option_and_state_endpoint(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    subs = tmp_path / "subs.srt"
    subs.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    client = make_client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/jobs",
        json={
            "source": str(source),
            "output": str(tmp_path / "out"),
            "transcript": str(subs),
            "cull_retakes": True,
        },
    )
    assert response.status_code == 202
    job = response.json()["job"]
    assert job["options"]["transcript"] == str(subs)
    assert job["options"]["cull_retakes"] is True
    wait_http(client, job["job_id"])
    state = client.get(f"/api/v1/jobs/{job['job_id']}/state")
    assert state.status_code == 200
    assert state.json()["retake_culls"] == [0]


def test_transcript_outside_the_jail_is_rejected(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/jobs",
        json={
            "source": str(source),
            "output": str(tmp_path / "out"),
            "transcript": "/etc/passwd",
            "cull_retakes": True,
        },
    )
    assert response.status_code == 403


def test_state_is_missing_before_a_run(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    client.post(
        "/api/v1/jobs",
        json={"source": str(source), "output": str(tmp_path / "out")},
    )
    # Fake runner writes state immediately; unknown job is the stable 404 case.
    assert client.get("/api/v1/jobs/missing/state").status_code == 404


def test_artifact_download_is_confined_to_the_job_output(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    job = client.post(
        "/api/v1/jobs",
        json={"source": str(source), "output": str(tmp_path / "out")},
    ).json()["job"]
    wait_http(client, job["job_id"])
    response = client.get(f"/api/v1/jobs/{job['job_id']}/artifacts/resolve")
    assert response.status_code == 200
    assert response.text == "<fcpxml/>"
    assert client.get(f"/api/v1/jobs/{job['job_id']}/artifacts/nope").status_code == 404


def test_job_reports_stages_and_logs(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    job = client.post(
        "/api/v1/jobs",
        json={"source": str(source), "output": str(tmp_path / "out")},
    ).json()["job"]
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


def test_new_module_options_are_forwarded(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/jobs",
        json={
            "source": str(source),
            "output": str(tmp_path / "out"),
            "min_speech_ms": 150,
            "vad_engine": "silero",
            "speech_threshold": 0.6,
            "speech_pad_before_ms": 80,
            "speech_pad_after_ms": 90,
            "offset_ms": 250,
            "crossfade_ms": 30,
            "handle_check": False,
            "zoom_mode": "manual_rules",
            "punch_in_scale": 1.2,
            "anchor_point": "center",
            "progressive_zoom": True,
            "pan_direction": "left_to_right",
            "export_targets": ["resolve"],
            "strictness": "aggressive",
            "retake_strategy": "keep_best",
            "context_window": 20,
            "shorts": True,
            "shorts_count": 2,
            "shorts_min_sec": 5,
            "shorts_max_sec": 10,
            "shorts_subtitles": False,
            "shorts_prompt": "pricing",
            "shorts_reprompt": "more energy",
            "shorts_prompt_mode": "refine",
            "shorts_hook_mode": "repeat",
            "shorts_remove_fillers": True,
            "shorts_filler_words": ["um", "uh"],
            "shorts_aspect": "1:1",
            "shorts_source_start_sec": 5,
            "shorts_source_end_sec": 50,
            "allow_external_services": True,
            "allowed_external_hosts": ["api.example.com"],
            "overrides": [{"sentence_id": 3, "action": "discard"}],
            "transcribe": True,
            "asr_base_url": "http://asr.local/v1",
            "asr_model": "whisper-1",
            "asr_language": "en",
            "whisper_model": "/models/ggml-small.bin",
            "caption_censor_enabled": True,
            "caption_censor_words": ["merda"],
            "caption_censor_replacement": "***",
            "audio_enhance": True,
            "audio_highpass_hz": 120,
            "audio_denoise_db": 18,
            "audio_target_lufs": -14.0,
            "overlay_enabled": True,
            "overlay_asset": "logo.png",
            "overlay_position": "top_left",
            "overlay_width_ratio": 0.2,
            "music_enabled": True,
            "music_asset": "track.mp3",
            "music_volume": 0.2,
            "music_ducking": False,
            "intro_enabled": True,
            "intro_asset": "intro.png",
            "intro_duration_sec": 1.5,
            "outro_enabled": True,
            "outro_asset": "outro.png",
            "caption_keyword_highlight_enabled": True,
            "caption_keyword_words": ["pricing"],
            "caption_emoji_enabled": True,
            "caption_emoji_map": {"money": "💰"},
            "caption_brand_vocabulary": {"video flow": "VideoFlow"},
        },
    )
    assert response.status_code == 202
    options = response.json()["job"]["options"]
    assert options["vad_engine"] == "silero"
    assert options["speech_threshold"] == 0.6
    assert options["speech_pad_before_ms"] == 80
    assert options["speech_pad_after_ms"] == 90
    assert options["offset_ms"] == 250
    assert options["export_targets"] == ["resolve"]
    assert options["context_window"] == 20
    assert options["shorts_count"] == 2
    assert options["shorts_prompt"] == "pricing"
    assert options["shorts_reprompt"] == "more energy"
    assert options["shorts_prompt_mode"] == "refine"
    assert options["shorts_hook_mode"] == "repeat"
    assert options["shorts_remove_fillers"] is True
    assert options["shorts_filler_words"] == ["um", "uh"]
    assert options["shorts_aspect"] == "1:1"
    assert options["caption_censor_enabled"] is True
    assert options["caption_censor_words"] == ["merda"]
    assert options["caption_keyword_highlight_enabled"] is True
    assert options["caption_keyword_words"] == ["pricing"]
    assert options["caption_emoji_map"] == {"money": "💰"}
    assert options["caption_brand_vocabulary"] == {"video flow": "VideoFlow"}
    assert options["audio_enhance"] is True
    assert options["audio_highpass_hz"] == 120
    assert options["audio_denoise_db"] == 18
    assert options["audio_target_lufs"] == -14.0
    assert options["overlay_enabled"] is True
    assert options["overlay_asset"] == "logo.png"
    assert options["overlay_position"] == "top_left"
    assert options["overlay_width_ratio"] == 0.2
    assert options["music_enabled"] is True
    assert options["music_asset"] == "track.mp3"
    assert options["music_volume"] == 0.2
    assert options["music_ducking"] is False
    assert options["intro_enabled"] is True
    assert options["intro_asset"] == "intro.png"
    assert options["intro_duration_sec"] == 1.5
    assert options["outro_enabled"] is True
    assert options["outro_asset"] == "outro.png"
    assert options["shorts_source_start_sec"] == 5
    assert options["shorts_source_end_sec"] == 50
    assert options["allow_external_services"] is True
    assert options["allowed_external_hosts"] == ["api.example.com"]
    assert options["overrides"] == [{"sentence_id": 3, "action": "discard"}]
    assert options["transcribe"] is True
    assert options["asr_language"] == "en"
    assert options["whisper_model"] == "/models/ggml-small.bin"


def test_unknown_job_is_404(monkeypatch, tmp_path: Path) -> None:
    client = make_client(monkeypatch, tmp_path)
    assert client.get("/api/v1/jobs/missing").status_code == 404
    assert client.post("/api/v1/jobs/missing/cancel").status_code == 404


def test_system_endpoint_reports_roots(monkeypatch, tmp_path: Path) -> None:
    client = make_client(monkeypatch, tmp_path)
    payload = client.get("/api/v1/system").json()
    assert payload["ok"] is True
    assert str(tmp_path) in payload["allowed_roots"]


def test_events_stream_delivers_the_terminal_state(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    client = make_client(monkeypatch, tmp_path)
    job = client.post(
        "/api/v1/jobs",
        json={"source": str(source), "output": str(tmp_path / "out")},
    ).json()["job"]
    wait_http(client, job["job_id"])
    response = client.get(f"/api/v1/jobs/{job['job_id']}/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"status": "succeeded"' in response.text


@pytest.mark.media
def test_real_job_writes_three_artifacts(monkeypatch, tmp_path: Path) -> None:
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("FFmpeg is not on PATH")
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=4",
            "-af",
            "volume=0:enable='between(t,1,2)'",
            "-t",
            "4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    client = TestClient(create_app())
    job = client.post(
        "/api/v1/jobs",
        json={"source": str(source), "output": str(tmp_path / "out")},
    ).json()["job"]
    finished = wait_http(client, job["job_id"], timeout=60)
    assert finished["status"] == "succeeded", finished
    for name in ("timeline.fcpxml", "timeline.xml", "timeline.kdenlive"):
        assert (tmp_path / "out" / "exports" / name).is_file()


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
    manager = JobManager()
    manager._jobs[str(job.job_id)] = job

    def fake_render(self, source, pieces, destination, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"edited")
        assert kwargs["width"] == 1080
        assert kwargs["height"] == 1080
        return destination

    monkeypatch.setattr(
        "videoflow.api.routes.FFmpegAdapter.render_short", fake_render
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
    manager = JobManager()
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
    manager = JobManager()
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
    manager = JobManager()
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
    manager = JobManager()
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
