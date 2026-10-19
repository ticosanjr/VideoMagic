import asyncio
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
