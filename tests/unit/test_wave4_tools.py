from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videoflow.application.jobs import JobManager
from videoflow.application.projects import init_project, save_project_state
from videoflow.application.session_brief import (
    build_session_brief,
    create_checkpoint,
    list_checkpoints,
    restore_checkpoint,
)
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    Sentence,
    VideoSegment,
    WordTiming,
)
from videoflow.domains.audio.diagnose import diagnose_audio
from videoflow.mcp_server.context import ToolContext
from videoflow.mcp_server.core_tools import register_core_tools

RATE = 48_000
FFMPEG = shutil.which("ffmpeg")


def _project(tmp_path: Path, monkeypatch, *, timeline: bool = True) -> object:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    record, _ = init_project(name="Wave 4", output=tmp_path / "out")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=300,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=RATE,
    )
    sentence = Sentence(
        id=0,
        start_sample=0,
        end_sample=2 * RATE,
        text="NVIDIA and Claude are in this sentence.",
        words=[
            WordTiming(
                word="NVIDIA",
                start_sample=0,
                end_sample=RATE,
                probability=0.9,
            )
        ],
    )
    state = ProjectState(
        media_info=media,
        sources={"primary": media},
        primary_source_id="primary",
        transcript=[sentence],
        video_segments=(
            [
                VideoSegment(
                    clip_id="v1",
                    source_id="primary",
                    source_in_frame=0,
                    source_out_frame=150,
                    timeline_in_frame=0,
                    timeline_out_frame=150,
                )
            ]
            if timeline
            else []
        ),
        audio_segments=(
            [
                AudioSegment(
                    clip_id="a1",
                    source_id="primary",
                    source_in_sample=0,
                    source_out_sample=2 * RATE,
                    timeline_in_sample=0,
                    timeline_out_sample=2 * RATE,
                )
            ]
            if timeline
            else []
        ),
    )
    state.pipeline.speech_intervals = [(0, 2 * RATE)]
    save_project_state(record, state, bump_revision=False)
    return record


def _tools(tmp_path: Path) -> dict[str, object]:
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager),
    )
    return tools


def test_session_brief_is_compact_and_lists_sources(
    tmp_path: Path, monkeypatch
) -> None:
    record = _project(tmp_path, monkeypatch)
    brief = build_session_brief(record.project_id)
    assert brief["ok"] is True
    assert brief["project_id"] == record.project_id
    assert brief["sources"][0]["id"] == "primary"
    assert brief["sources"][0]["duration_sec"] == 10.0
    assert brief["next_actions"]
    assert "transcript" not in brief
    assert len(str(brief)) < 4000


def test_named_checkpoints_create_list_and_restore(
    tmp_path: Path, monkeypatch
) -> None:
    record = _project(tmp_path, monkeypatch)
    created = create_checkpoint(record.project_id, "pos_broll")
    assert created["ok"] is True
    assert created["label"] == "pos_broll"
    listed = list_checkpoints(record.project_id)
    assert listed["count"] == 1
    assert listed["checkpoints"][0]["label"] == "pos_broll"
    restored = restore_checkpoint(record.project_id, "pos_broll")
    assert restored["ok"] is True
    assert restored["revision"] > created["revision"]


def test_transcript_query_filters_and_pages(tmp_path: Path, monkeypatch) -> None:
    record = _project(tmp_path, monkeypatch)
    tools = _tools(tmp_path)
    result = tools["vf_transcript_query"](
        project_id=record.project_id,
        query="nvidia",
        limit=1,
    )
    assert result["ok"] is True
    assert result["count"] == 1
    assert result["sentences"][0]["text"].startswith("NVIDIA")
    assert result["next_cursor"] is None

    words = tools["vf_transcript_query"](
        project_id=record.project_id,
        include_words=True,
    )
    assert words["sentences"][0]["words"][0]["word"] == "NVIDIA"


def test_consolidated_tool_paths(tmp_path: Path, monkeypatch) -> None:
    record = _project(tmp_path, monkeypatch)
    tools = _tools(tmp_path)
    assert tools["vf_job"](action="list")["ok"] is True
    assert tools["vf_assets"](action="fonts")["ok"] is True
    assert tools["vf_project"](action="session_brief", project_id=record.project_id)["ok"] is True


def test_glossary_upserts_and_applies_technical_terms(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    tools = _tools(tmp_path)
    upserted = tools["vf_glossary"](
        action="upsert",
        channel_id="tech",
        terms=[{"canonical": "Claude", "variants": ["clódi"]}],
    )
    assert upserted["ok"] is True
    assert any(item["canonical"] == "Claude" for item in upserted["terms"])

    applied = tools["vf_glossary"](
        action="apply",
        channel_id="tech",
        text="clódi e invídia",
    )
    assert applied["ok"] is True
    assert applied["text"] == "Claude e NVIDIA"
    assert applied["applied"] == 2


def test_overlay_update_and_remove(tmp_path: Path, monkeypatch) -> None:
    record = _project(tmp_path, monkeypatch)
    asset = tmp_path / "logo.png"
    asset.write_bytes(b"png")
    tools = _tools(tmp_path)
    added = tools["vf_overlay"](
        project_id=record.project_id,
        asset_path=str(asset),
        at_timeline_sec=0.0,
        duration_sec=1.0,
        anchor="bottom_left",
    )
    assert added["ok"] is True, added
    overlay_id = added["overlay"]["overlay_id"]
    updated = tools["vf_overlay"](
        action="update",
        project_id=record.project_id,
        overlay_id=overlay_id,
        margin_x=64,
        margin_y=64,
    )
    assert updated["ok"] is True, updated
    assert updated["overlay"]["margin_x"] == 64
    assert updated["overlay"]["margin_y"] == 64
    removed = tools["vf_overlay"](
        action="remove",
        project_id=record.project_id,
        overlay_id=overlay_id,
    )
    assert removed["ok"] is True
    listed = tools["vf_overlay"](action="list", project_id=record.project_id)
    assert listed["count"] == 0


def test_semantic_retake_candidates_are_delegated() -> None:
    from videoflow.application.editorial_clean import _semantic_candidates

    sentences = [
        Sentence(id=0, start_sample=0, end_sample=RATE, text="vamos falar de nvidia"),
        Sentence(
            id=1,
            start_sample=RATE,
            end_sample=2 * RATE,
            text="vamos falar de nvidia hoje",
        ),
    ]
    candidates, inspected = _semantic_candidates(
        sentences,
        block_size=8,
        overlap=4,
    )
    assert inspected == 1
    assert candidates
    assert candidates[0]["sentence_id"] == 0
    assert candidates[0]["keeper_id"] == 1


def test_preflight_plan_reports_timeline_and_clip_blockers(
    tmp_path: Path, monkeypatch
) -> None:
    record = _project(tmp_path, monkeypatch, timeline=False)
    tools = _tools(tmp_path)
    export = tools["vf_preflight_plan"](
        project_id=record.project_id,
        operation="export",
        params={"targets": ["mp4"]},
    )
    assert export["ok"] is False
    assert any(item["code"] == "timeline_required" for item in export["blockers"])
    assert export["plan"]

    shorts = tools["vf_preflight_plan"](
        project_id=record.project_id,
        operation="shorts_batch",
        params={},
    )
    assert any(item["code"] == "clips_required" for item in shorts["blockers"])
    assert any(item["code"] == "unknown_param" for item in shorts["warnings"]) is False


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_storyboard_strip_creates_one_png(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.mp4"
    completed = subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=30:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    record, _ = init_project(name="Storyboard", output=tmp_path / "out")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=60,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )
    state = ProjectState(
        media_info=media,
        sources={"primary": media},
        primary_source_id="primary",
    )
    save_project_state(record, state, bump_revision=False)
    tools = _tools(tmp_path)
    result = tools["vf_storyboard_strip"](
        project_id=record.project_id,
        start_sec=0,
        end_sec=2,
    )
    assert result["ok"] is True, result
    path = Path(result["storyboard"]["path"])
    assert path.is_file()
    assert path.suffix == ".png"
    assert result["storyboard"]["frames"] >= 1


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_audio_diagnosis_detects_left_only_mono(tmp_path: Path) -> None:
    source = tmp_path / "left.wav"
    completed = subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=1",
            "-af",
            "pan=stereo|c0=c0|c1=0*c0",
            "-c:a",
            "pcm_s24le",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    diagnosis = diagnose_audio(source)
    assert diagnosis["mono_left_only"] is True
    assert diagnosis["mono_repair_recommended"] is True
    assert diagnosis["sample_rate"] == 48000
