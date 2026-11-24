"""Cross-process projects, curation, timeline totals and delivery collection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.unit.test_core_tools import setup
from videoflow.api.app import create_app
from videoflow.application import database
from videoflow.application.curation_board import (
    active_server_path,
    board_url,
)
from videoflow.application.output_layout import collect_outputs
from videoflow.application.projects import (
    ProjectAmbiguousError,
    init_project,
    resolve_project_ref,
    save_project_state,
)
from videoflow.domain.state import AudioSegment, VideoSegment
from videoflow.mcp_server.server import build_server


def _items(project_output: Path) -> list[dict[str, object]]:
    media = project_output / "assets" / "curation"
    media.mkdir(parents=True, exist_ok=True)
    (media / "bed.wav").write_bytes(b"fixture")
    (media / "broll.mp4").write_bytes(b"fixture")
    return [
        {
            "item_id": "music-1",
            "category": "music",
            "title": "Bed",
            "media_type": "audio",
            "local_path": "assets/curation/bed.wav",
            "recommended": True,
        },
        {
            "item_id": "broll-1",
            "category": "broll",
            "title": "B-roll",
            "media_type": "video",
            "local_path": "assets/curation/broll.mp4",
        },
    ]


def _call(server, name: str, arguments: dict) -> dict:
    import asyncio

    async def run() -> dict:
        result = await server.call_tool(name, arguments)
        return result.structured_content  # type: ignore[attr-defined]

    return asyncio.run(run())


def test_projects_table_indexes_slug_name_output_and_imports_legacy(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    database.upsert_project(
        "p1",
        {
            "project_id": "p1",
            "name": "One",
            "output": str(tmp_path / "one"),
        },
    )
    with database.connect() as connection:
        row = connection.execute(
            "SELECT slug, name, output_dir, payload_json FROM projects WHERE project_id='p1'"
        ).fetchone()
    assert row is not None
    assert row[0] == "p1"
    assert row[1] == "One"
    assert row[2] == str(tmp_path / "one")
    assert json.loads(row[3])["project_id"] == "p1"

    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "projects.json").write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "project_id": "legacy",
                        "name": "Legacy",
                        "output": str(tmp_path / "legacy"),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert any(item["project_id"] == "legacy" for item in database.list_projects())


def test_names_are_not_resolved_and_duplicate_output_folders_are_ambiguous(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    init_project(
        project_id="first",
        name="Episode",
        output=tmp_path / "a" / "shared",
    )
    init_project(
        project_id="second",
        name="Episode",
        output=tmp_path / "b" / "shared",
    )
    with pytest.raises(ProjectAmbiguousError) as captured:
        resolve_project_ref("shared")
    assert captured.value.code == "project_ambiguous"


def test_mcp_board_is_decided_by_api_and_read_back_by_mcp(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    record, _ = init_project(
        project_id="cross-process",
        name="Cross",
        output=tmp_path / "cross",
    )
    server = build_server()
    published = _call(
        server,
        "vf_curation",
        {
            "action": "publish",
            "project_id": record.project_id,
            "items": _items(Path(record.output)),
        },
    )
    assert published["ok"] is True
    assert published["board_url"].endswith("/#curation/cross-process")

    client = TestClient(create_app())
    decided = client.post(
        "/api/v1/curation/cross-process/decide",
        json={"selected_ids": ["music-1"], "rejected_ids": ["broll-1"]},
    )
    assert decided.status_code == 200
    assert decided.json()["decisions"]["status"] == "decided"

    read = _call(
        server,
        "vf_curation",
        {"action": "read", "project_id": "cross-process"},
    )
    assert read["ok"] is True
    assert read["status"] == "decided"
    assert [item["item_id"] for item in read["selected"]] == ["music-1"]


def test_board_url_uses_active_server_port(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    active_server_path().parent.mkdir(parents=True, exist_ok=True)
    active_server_path().write_text(
        json.dumps({"host": "127.0.0.1", "port": 8766}),
        encoding="utf-8",
    )
    assert board_url("demo") == "http://127.0.0.1:8766/#curation/demo"


def test_delivery_collect_includes_master_short_and_nle_files(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VF_OUTPUT_DIR", str(tmp_path / "delivery"))
    output = tmp_path / "project"
    (output / "exports" / "qa").mkdir(parents=True)
    (output / "shorts" / "batch").mkdir(parents=True)
    files = [
        "exports/youtube_master.mp4",
        "exports/preview_fast.mp4",
        "exports/timeline.fcpxml",
        "exports/timeline.xml",
        "exports/timeline.kdenlive",
        "exports/timeline.mlt",
        "exports/qa/qa_report.json",
        "shorts/batch/short-01.mp4",
        "shorts/batch/short-01.ass",
    ]
    for relative in files:
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    result = collect_outputs(
        output,
        project_id="paula-ep-10",
        mode="copy",
    )
    root = tmp_path / "delivery" / "paula-ep-10"
    for relative in files:
        destination = root / relative
        assert destination.is_file(), relative
    assert result["count"] >= len(files)


def _state_with_clips(tmp_path: Path, count: int = 62):
    from videoflow.domain.state import MediaInfo, ProjectState

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    total_frames = 25_804  # 860.133s at 30 fps
    base_frames = total_frames // count
    remainder = total_frames - base_frames * count
    media = MediaInfo(
        source_path=str(source),
        duration_frames=total_frames,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48_000,
    )
    video: list[VideoSegment] = []
    audio: list[AudioSegment] = []
    cursor_frame = 0
    cursor_sample = 0
    for index in range(count):
        frames = base_frames + (remainder if index == count - 1 else 0)
        samples = frames * 1_600
        video.append(
            VideoSegment(
                clip_id=f"v{index}",
                source_id="src1",
                source_in_frame=0,
                source_out_frame=frames,
                timeline_in_frame=cursor_frame,
                timeline_out_frame=cursor_frame + frames,
            )
        )
        audio.append(
            AudioSegment(
                clip_id=f"v{index}",
                source_id="src1",
                source_in_sample=0,
                source_out_sample=samples,
                timeline_in_sample=cursor_sample,
                timeline_out_sample=cursor_sample + samples,
            )
        )
        cursor_frame += frames
        cursor_sample += samples
    return ProjectState(
        sources={"src1": media},
        primary_source_id="src1",
        media_info=media,
        video_segments=video,
        audio_segments=audio,
    )


def test_vf_timeline_returns_totals_and_paginates(monkeypatch, tmp_path: Path) -> None:
    tools, record, _job = setup(tmp_path, monkeypatch)
    state = _state_with_clips(tmp_path)
    save_project_state(record, state, bump_revision=False)
    page = tools["vf_timeline"](
        action="get",
        project_id=record.project_id,
        page=1,
        page_size=30,
    )
    assert page["ok"] is True
    assert page["total_clips"] == 62
    assert page["total_duration_sec"] == 860.133
    assert page["page"] == 1
    assert page["page_size"] == 30
    assert page["has_more"] is True
    assert len(page["video"]) == 30
    assert len(page["audio"]) == 30

    last = tools["vf_timeline"](
        action="get",
        project_id=record.project_id,
        page=3,
        page_size=30,
    )
    assert len(last["video"]) == 2
    assert last["has_more"] is False


def test_vf_audio_master_invokes_audio_finalize(
    monkeypatch, tmp_path: Path
) -> None:
    tools, record, _job = setup(tmp_path, monkeypatch)

    def fake_run(self, context, params, io):
        context.artifacts["audio_final"] = str(Path(record.output) / "audio" / "final.wav")
        context.artifacts["audio_final_mix"] = str(
            Path(record.output) / "audio" / "final_mix.wav"
        )
        context.artifacts["audio_master"] = str(Path(record.output) / "audio" / "master.wav")
        context.metadata["audio_finalize"] = {"ok": True}

    monkeypatch.setattr(
        "videoflow.steps.audio_finalize.AudioFinalizeStep.run",
        fake_run,
    )
    result = tools["vf_audio"](
        action="master",
        project_id=record.project_id,
        target_lufs=-16.0,
    )
    assert result["ok"] is True
    assert result["audio_final"].endswith("final.wav")
    assert result["finalize"] == {"ok": True}
