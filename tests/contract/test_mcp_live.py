import asyncio
import json
import time
from pathlib import Path

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.jobs import JobManager
from videoflow.domain.state import MediaInfo
from videoflow.mcp_server.server import build_server


def fake_runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
    progress("done", 100, "done")
    return {"ok": True, "video_segment_count": 2}


def media(path: Path) -> MediaInfo:
    return MediaInfo(
        source_path=str(path),
        duration_frames=90,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=48000,
    )


def call(server: object, name: str, arguments: dict) -> dict:
    async def run() -> dict:
        result = await server.call_tool(name, arguments)  # type: ignore[attr-defined]
        return result.structured_content  # type: ignore[attr-defined]

    return asyncio.run(run())


def test_load_media_and_run_a_job(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    monkeypatch.setattr(
        FFmpegAdapter,
        "probe",
        lambda self, path: media(Path(path)),
    )
    manager = JobManager(fake_runner)
    server = build_server(manager)

    loaded = call(server, "videoflow_load_media", {"file_path": str(source)})
    assert loaded["ok"] is True
    assert loaded["media"]["duration_frames"] == 90

    started = call(
        server,
        "videoflow_run_pipeline",
        {"preset_name": "lecture-clean", "output": str(tmp_path / "out")},
    )
    assert started["ok"] is True
    job_id = started["job"]["job_id"]
    deadline = time.time() + 3
    while time.time() < deadline:
        job = call(server, "videoflow_get_job", {"job_id": job_id})
        if job["job"]["status"] == "succeeded":
            break
        time.sleep(0.01)
    assert job["job"]["status"] == "succeeded"
    assert job["job"]["options"]["zooms"] is False


def test_load_media_rejects_a_path_outside_the_jail(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    server = build_server(JobManager(fake_runner))
    payload = call(server, "videoflow_load_media", {"file_path": "/etc/passwd"})
    assert payload["code"] == "path_not_allowed"


def test_unknown_job_and_invalid_preset(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    server = build_server(JobManager(fake_runner))
    missing = call(server, "videoflow_get_job", {"job_id": "missing"})
    assert missing["code"] == "job_not_found"
    bad = call(
        server,
        "videoflow_run_pipeline",
        {"preset_name": "nope", "source": str(source), "output": str(tmp_path / "out")},
    )
    assert bad["code"] == "invalid_overrides"


def test_granular_tools_analyse_and_stage_options(monkeypatch, tmp_path: Path) -> None:
    from videoflow.domain.state import Sentence
    from videoflow.mcp_server import server as server_module

    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    monkeypatch.setattr(FFmpegAdapter, "probe", lambda self, path: media(Path(path)))
    monkeypatch.setattr(
        FFmpegAdapter,
        "extract_pcm",
        lambda self, source, destination, *, sample_rate=16000: _touch(destination),
    )
    monkeypatch.setattr(
        FFmpegAdapter,
        "detect_speech",
        lambda self, wav, **kwargs: [(0, 48000), (96000, 144000)],
    )

    class FakeWhisper:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def transcribe(self, wav_path: Path, sample_rate: int) -> list[Sentence]:
            return [
                Sentence(id=0, start_sample=0, end_sample=48000, text="First sentence."),
                Sentence(id=1, start_sample=96000, end_sample=144000, text="Second sentence."),
            ]

    monkeypatch.setattr(server_module, "WhisperCliAdapter", FakeWhisper)
    manager = JobManager(fake_runner)
    server = build_server(manager)

    assert call(server, "videoflow_load_media", {"file_path": str(source)})["ok"] is True
    vad = call(server, "videoflow_run_vad", {"noise_db": -30, "min_silence_ms": 400})
    assert vad["ok"] is True
    assert vad["interval_count"] == 2
    assert vad["speech_seconds"] == 2.0

    transcribed = call(server, "videoflow_transcribe", {"model": "tiny", "language": "en"})
    assert transcribed["ok"] is True
    assert transcribed["source"] == "whisper"
    assert transcribed["sentence_count"] == 2

    transcript = call(server, "videoflow_get_transcript", {})
    assert transcript["ok"] is True
    assert "First sentence." in transcript["srt"]
    assert len(transcript["transcript"][0]["words"]) == 0

    zooms = call(server, "videoflow_configure_zooms", {"mode": "manual_rules", "scale": 1.2})
    assert zooms["ok"] is True
    jcuts = call(server, "videoflow_apply_jcuts", {"offset_ms": 250, "crossfade_ms": 30})
    assert jcuts["ok"] is True
    culled = call(
        server,
        "videoflow_cull_retakes",
        {"discard_sentence_ids": [1]},
    )
    assert culled["ok"] is True
    assert 1 in culled["discard_sentence_ids"]

    shorts = call(
        server,
        "videoflow_generate_shorts",
        {"min_duration": 1, "max_duration": 60, "count": 2},
    )
    assert shorts["ok"] is True
    assert all(1 not in clip["sentence_ids"] for clip in shorts["clips"])

    started = call(
        server,
        "videoflow_run_pipeline",
        {"output": str(tmp_path / "out"), "source": str(source)},
    )
    assert started["ok"] is True
    options = started["job"]["options"]
    assert options["zooms"] is True
    assert options["zoom_mode"] == "manual_rules"
    assert options["offset_ms"] == 250
    assert options["cull_retakes"] is True
    assert options["overrides"] == [{"sentence_id": 1, "action": "discard"}]


def test_state_resources_and_export_use_the_completed_job(monkeypatch, tmp_path: Path) -> None:
    from videoflow.domain.state import ProjectState, Sentence
    from videoflow.mcp_server import server as server_module

    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    media_info = media(source)
    state = ProjectState(
        media_info=media_info,
        transcript=[
            Sentence(id=0, start_sample=0, end_sample=48000, text="First sentence."),
            Sentence(id=1, start_sample=96000, end_sample=144000, text="Second sentence."),
        ],
        retake_culls=[1],
    )

    def state_runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        output.mkdir(parents=True, exist_ok=True)
        (output / "project_state.json").write_text(state.model_dump_json(), encoding="utf-8")
        artifacts = {}
        for target, name in (("resolve", "timeline.fcpxml"), ("premiere", "timeline.xml")):
            path = output / name
            path.write_text("artifact", encoding="utf-8")
            artifacts[target] = str(path)
        (output / "run.json").write_text(
            json.dumps({"ok": True, "artifacts": artifacts}), encoding="utf-8"
        )
        progress("done", 100, "done")
        return {"ok": True, "artifacts": artifacts}

    manager = JobManager(state_runner)
    server = build_server(manager)
    monkeypatch.setattr(FFmpegAdapter, "probe", lambda self, path: media(Path(path)))
    call(server, "videoflow_load_media", {"file_path": str(source)})
    started = call(
        server,
        "videoflow_run_pipeline",
        {"output": str(tmp_path / "out"), "source": str(source)},
    )
    job_id = started["job"]["job_id"]
    deadline = time.time() + 3
    while time.time() < deadline:
        job = call(server, "videoflow_get_job", {"job_id": job_id})
        if job["job"]["status"] == "succeeded":
            break
        time.sleep(0.01)
    assert job["job"]["status"] == "succeeded"

    transcript = call(server, "videoflow_get_transcript", {"include_word_timestamps": False})
    assert transcript["sentence_count"] == 2
    assert "Second sentence." in transcript["srt"]

    shorts = call(
        server,
        "videoflow_generate_shorts",
        {"min_duration": 1, "max_duration": 60, "count": 1},
    )
    assert shorts["ok"] is True
    assert shorts["count"] == 1

    def fake_export(state_arg, directory, *, targets, dialect="1.9"):
        path = Path(directory) / server_module.FILENAMES[targets[0]]
        path.write_text("exported", encoding="utf-8")
        return {targets[0]: path}

    monkeypatch.setattr(server_module, "export_timeline", fake_export)
    exported = call(
        server,
        "videoflow_export_fcpxml",
        {"output_path": str(tmp_path / "custom.fcpxml"), "target_nle": "resolve"},
    )
    assert exported["ok"] is True
    assert (tmp_path / "custom.fcpxml").read_text() == "exported"

    async def read(uri: str) -> str:
        contents = await server.read_resource(uri)  # type: ignore[attr-defined]
        return next(iter(contents)).content  # type: ignore[attr-defined]

    state_payload = json.loads(asyncio.run(read("videoflow://project/state")))
    assert state_payload["transcript"][0]["text"] == "First sentence."
    transcript_payload = asyncio.run(read("videoflow://project/transcript"))
    assert "00:00:02,000 --> 00:00:03,000" in transcript_payload
    exports_payload = json.loads(asyncio.run(read("videoflow://project/exports")))
    assert exports_payload["exports"]["resolve"]["exists"] is True


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF")
    return path
