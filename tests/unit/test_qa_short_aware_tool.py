from __future__ import annotations

import json
from pathlib import Path

from videoflow.application.jobs import JobManager
from videoflow.application.projects import init_project, save_project_state
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    Sentence,
    VideoSegment,
)
from videoflow.engine.batch import BatchManager
from videoflow.mcp_server.context import ToolContext
from videoflow.mcp_server.core_tools import register_core_tools

RATE = 48_000


def _tools(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    record, _ = init_project(name="QA", output=tmp_path / "out")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=1800,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=RATE,
    )
    state = ProjectState(
        media_info=media,
        sources={"primary": media},
        primary_source_id="primary",
        transcript=[Sentence(id=0, start_sample=0, end_sample=10 * RATE, text="texto")],
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_id="primary",
                source_in_frame=0,
                source_out_frame=1800,
                timeline_in_frame=0,
                timeline_out_frame=1800,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="a1",
                source_id="primary",
                source_in_sample=0,
                source_out_sample=10 * RATE,
                timeline_in_sample=0,
                timeline_out_sample=10 * RATE,
            )
        ],
    )
    save_project_state(record, state, bump_revision=False)
    short = Path(record.output) / "shorts" / "batch" / "one.mp4"
    short.parent.mkdir(parents=True, exist_ok=True)
    short.write_bytes(b"short")
    subtitles = short.with_suffix(".ass")
    subtitles.write_text("[Events]\n", encoding="utf-8")
    (short.parent / "shorts_batch.json").write_text(
        json.dumps(
            {
                "ok": True,
                "clips": [
                    {
                        "title": "One",
                        "path": str(short),
                        "start_sec": 1.0,
                        "end_sec": 4.0,
                        "aspect_ratio": "4:5",
                        "fps": 30,
                        "subtitles": str(subtitles),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager, batch_manager=BatchManager(manager)),
    )
    return tools, record, short


def test_qa_final_detects_a_short_and_uses_its_window(
    tmp_path: Path, monkeypatch
) -> None:
    tools, record, short = _tools(tmp_path, monkeypatch)
    captured: dict[str, object] = {}

    def fake_audit(video, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "status": "succeeded", "issues": []}

    monkeypatch.setattr("videoflow.application.qa_final.audit_final", fake_audit)
    result = tools["vf_qa_final"](
        project_id=record.project_id,
        video_path=str(short),
        mode="fast",
    )
    assert result["ok"] is True
    assert captured["window_sec"] == (1.0, 4.0)
    assert captured["expected_sec"] == 3.0
    assert captured["fps"] == 30.0
    assert captured["width"] == 1080
    assert captured["height"] == 1350
    assert captured["caption_path"] == short.with_suffix(".ass")
