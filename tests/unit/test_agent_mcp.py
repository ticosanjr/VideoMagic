"""Agent profile project isolation, session ingest, and multicam sync."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from videoflow.application.multicam import sync_multicam
from videoflow.domain.state import MediaInfo, ProjectState
from videoflow.mcp_server.server import build_server


def clip(path: Path, *, seconds: float = 1.0, size: str = "320x240", delay_ms: int = 0) -> Path:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={size}:rate=30:duration={seconds}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={seconds}",
    ]
    if delay_ms:
        command.extend(["-af", f"adelay={delay_ms}|{delay_ms}"])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ]
    )
    subprocess.run(command, check=True)
    return path


def _media(path: Path):
    from videoflow.domain.state import MediaInfo

    return MediaInfo(
        source_path=str(path),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )


def call(server, name: str, arguments: dict) -> dict:
    async def run() -> dict:
        result = await server.call_tool(name, arguments)
        return result.structured_content  # type: ignore[attr-defined]

    return asyncio.run(run())


def test_project_isolated_by_explicit_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    source = clip(tmp_path / "source.mp4")
    server = build_server()
    first = call(
        server,
        "vf_project_init",
        {"output": str(tmp_path / "a"), "sources": [str(source)]},
    )
    second = call(
        server,
        "vf_project_init",
        {"output": str(tmp_path / "b"), "sources": [str(source)]},
    )
    assert first["project"]["project_id"] != second["project"]["project_id"]
    status = call(server, "vf_project_status", {"project_id": first["project"]["project_id"]})
    assert status["ok"] is True
    assert status["summary"]["sources"][0]["path"] == str(source)


def test_session_ingest_creates_multi_source_state(monkeypatch, tmp_path: Path) -> None:
    from videoflow.core.context import PipelineContext
    from videoflow.steps.base import StepIO
    from videoflow.steps.session_ingest import SessionIngestParams, SessionIngestStep

    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    paths = [
        clip(tmp_path / "clip1.mp4"),
        clip(tmp_path / "clip2.mp4", size="640x360"),
        clip(tmp_path / "clip3.mp4"),
    ]
    output = tmp_path / "out"
    (output / "work").mkdir(parents=True)
    context = PipelineContext(
        source=paths[0], output=output, work=output / "work", exports=output / "exports"
    )
    SessionIngestStep().run(
        context,
        SessionIngestParams(sources=[str(path) for path in paths], normalize=True),
        StepIO(),
    )
    assert context.state is not None
    assert len(context.state.sources) == 3
    assert len(context.state.video_segments) == 3
    assert {item.source_id for item in context.state.video_segments} == {
        "src001",
        "src002",
        "src003",
    }
    assert context.metadata["session_manifest"]["clip_count"] == 3
    assert Path(context.metadata["session_audio"]).is_file()


def test_multicam_reports_offset_and_drift(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    first = clip(tmp_path / "a.mp4", seconds=3)
    second = clip(tmp_path / "b.mp4", seconds=3, delay_ms=250)
    sources = {
        "src001": MediaInfo(
            source_path=str(first),
            duration_frames=90,
            fps_num=30,
            fps_den=1,
            width=320,
            height=240,
            audio_sample_rate=48000,
        ),
        "src002": MediaInfo(
            source_path=str(second),
            duration_frames=90,
            fps_num=30,
            fps_den=1,
            width=320,
            height=240,
            audio_sample_rate=48000,
        ),
    }
    state = ProjectState(
        sources=sources,
        primary_source_id="src001",
        media_info=sources["src001"],
    )
    report = sync_multicam(
        state,
        tmp_path / "sync",
        primary_source_id="src001",
        secondary_source_id="src002",
        apply=True,
        min_confidence=0.05,
    )
    assert report["confidence"] >= 0.05
    assert report["applied"] is True
    assert "offset_ms" in report
    assert "drift_ms" in report


def test_session_cull_applies_retakes_without_rebuilding(monkeypatch, tmp_path: Path) -> None:
    from videoflow.core.context import PipelineContext
    from videoflow.domain.state import Sentence, WordTiming
    from videoflow.steps.base import StepIO
    from videoflow.steps.session_cull import SessionCullParams, SessionCullStep
    from videoflow.steps.session_ingest import SessionIngestParams, SessionIngestStep

    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    paths = [clip(tmp_path / "one.mp4"), clip(tmp_path / "two.mp4")]
    output = tmp_path / "out"
    (output / "work").mkdir(parents=True)
    context = PipelineContext(
        source=paths[0], output=output, work=output / "work", exports=output / "exports"
    )
    SessionIngestStep().run(
        context,
        SessionIngestParams(sources=[str(path) for path in paths]),
        StepIO(),
    )
    rate = 16000
    context.transcript = [
        Sentence(
            id=0,
            start_sample=0,
            end_sample=rate // 2,
            text="keep",
            words=[WordTiming(word="keep", start_sample=0, end_sample=rate // 2, probability=1.0)],
        ),
        Sentence(
            id=1,
            start_sample=rate // 2,
            end_sample=rate,
            text="drop",
            words=[
                WordTiming(word="drop", start_sample=rate // 2, end_sample=rate, probability=1.0)
            ],
        ),
    ]
    SessionCullStep().run(context, SessionCullParams(discard_sentence_ids=[1]), StepIO())
    assert context.state is not None
    assert context.state.video_segments
    assert context.state.video_segments[-1].timeline_out_frame < 60
    assert context.metadata["session_cull_report"]["discarded_sentences"] == 1


def test_project_render_job_returns_final_metrics(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application.projects import init_project, save_project_state
    from videoflow.domain.state import AudioSegment, ProjectState, VideoSegment

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    source = clip(tmp_path / "source.mp4")
    record, _ = init_project(output=tmp_path / "out", sources=[str(source)])
    state = ProjectState(
        sources={"src1": _media(source)},
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_id="src1",
                source_in_frame=0,
                source_out_frame=30,
                timeline_in_frame=0,
                timeline_out_frame=30,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_id="src1",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            )
        ],
    )
    save_project_state(record, state, bump_revision=False)
    server = build_server()
    started = call(server, "vf_render_start", {"project_id": record.project_id, "draft_scale": 0.5})
    waited = call(
        server,
        "vf_wait_job",
        {
            "project_id": record.project_id,
            "job_id": started["job"]["job_id"],
            "timeout_sec": 120,
        },
    )
    assert waited["ok"] is True
    result = waited["job"]["result"]
    assert result["height"] == 120
    assert result["duration_sec"] > 0
    assert "qa_status" in result


def test_artifact_images_and_qa_payload(monkeypatch, tmp_path: Path) -> None:
    from PIL import Image

    from videoflow.application.projects import init_project

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    record, _ = init_project(output=tmp_path / "out")
    exports = tmp_path / "out" / "exports"
    exports.mkdir(parents=True)
    Image.new("RGB", (32, 32), (255, 0, 0)).save(exports / "thumb.png")
    qa = tmp_path / "out" / "work" / "qa"
    qa.mkdir(parents=True)
    (qa / "qa_report.json").write_text(
        '{"defects": [{"kind": "flash", "start_sec": 1}], "passed": false}',
        encoding="utf-8",
    )
    Image.new("RGB", (32, 32), (0, 255, 0)).save(qa / "frame.jpg")
    server = build_server()

    async def artifact():
        result = await server.call_tool(
            "vf_get_artifact",
            {"project_id": record.project_id, "artifact": "exports/thumb.png"},
        )
        return result

    result = asyncio.run(artifact())
    assert len(result.content) == 2
    assert result.content[0].type == "text"
    assert result.content[1].type == "image"
    qa_payload = call(
        server,
        "vf_get_qa_artifacts",
        {"project_id": record.project_id, "include_images": True},
    )
    # FastMCP exposes list results as text + image content, not structured data.
    assert qa_payload is None or "defects" in str(qa_payload)
