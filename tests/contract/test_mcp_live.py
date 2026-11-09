import asyncio
import json
import time
from pathlib import Path

from tests.recipe_jobs import manager_with_runner, start_recipe
from videoflow.adapters.ffmpeg import FFmpegAdapter
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
    manager = manager_with_runner(fake_runner)
    server = build_server(manager)

    loaded = call(server, "videoflow_load_media", {"file_path": str(source)})
    assert loaded["ok"] is True
    assert loaded["media"]["duration_frames"] == 90

def test_load_media_rejects_a_path_outside_the_jail(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    server = build_server(manager_with_runner(fake_runner))
    payload = call(server, "videoflow_load_media", {"file_path": "/etc/passwd"})
    assert payload["code"] == "path_not_allowed"


def test_unknown_job_and_invalid_preset(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    server = build_server(manager_with_runner(fake_runner))
    missing = call(server, "videoflow_get_job", {"job_id": "missing"})
    assert missing["code"] == "job_not_found"



def test_state_resources_and_export_use_the_completed_job(monkeypatch, tmp_path: Path) -> None:
    from videoflow.domain.state import ProjectState, Sentence
    from videoflow.mcp_server import tools_media as media_module

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

    manager = manager_with_runner(state_runner)
    server = build_server(manager)
    monkeypatch.setattr(FFmpegAdapter, "probe", lambda self, path: media(Path(path)))
    call(server, "videoflow_load_media", {"file_path": str(source)})
    started_job = start_recipe(manager, source, tmp_path / "out", queue=True)
    server.videoflow_last.update(  # type: ignore[attr-defined]
        source=source, output=started_job.output, job_id=str(started_job.job_id)
    )
    job_id = str(started_job.job_id)
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

    def fake_export(state_arg, directory, *, targets, dialect="1.9"):
        path = Path(directory) / media_module.FILENAMES[targets[0]]
        path.write_text("exported", encoding="utf-8")
        return {targets[0]: path}

    monkeypatch.setattr(media_module, "export_timeline", fake_export)
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
