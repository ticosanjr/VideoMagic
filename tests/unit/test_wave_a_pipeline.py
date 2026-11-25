from __future__ import annotations

import contextlib
import time
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import BaseModel

from videoflow.application.beatmap import BeatmapError, apply_beatmap
from videoflow.application.pipeline_state import (
    context_from_pipeline,
    update_pipeline_from_context,
)
from videoflow.application.projects import (
    get_project,
    init_project,
    load_project_state,
    save_project_state,
)
from videoflow.application.revisions import create_snapshot, list_snapshots, load_snapshot
from videoflow.application.shorts import ShortClip
from videoflow.application.time_map import (
    TimeMapError,
    source_range_to_timeline,
    source_to_timeline_sec,
    timeline_to_source_sec,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    VideoSegment,
)
from videoflow.steps.base import BaseStep, EmptyParams, StepIO
from videoflow.steps.registry import register_step


def _state(tmp_path: Path) -> ProjectState:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=1800,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )
    return ProjectState(
        media_info=media,
        sources={"primary": media},
        primary_source_id="primary",
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
                source_out_sample=2_880_000,
                timeline_in_sample=0,
                timeline_out_sample=2_880_000,
            )
        ],
    )


def test_pipeline_context_roundtrip_and_checkpoint(tmp_path: Path) -> None:
    record, state = init_project(name="State", output=tmp_path / "project")
    context = PipelineContext(
        source=tmp_path,
        output=Path(record.output),
        work=Path(record.output) / "work",
        exports=Path(record.output) / "exports",
        state=state,
    )
    context.selected_shorts = [
        ShortClip(
            title="Hook",
            start_sample=0,
            end_sample=48000,
            sentence_ids=(1,),
            pieces=((0, 48000),),
        )
    ]
    context.short_captions = {"Hook": str(tmp_path / "hook.ass")}
    context.pcm_path = tmp_path / "source.wav"
    context.pcm_digest = "abc"
    context.discard_sentence_ids = [7]
    context.metadata["applied_style_id"] = "sr-x-native-video-card"

    updated = update_pipeline_from_context(state, context, step="transcribe")
    saved = save_project_state(record, updated, bump_revision=False)
    loaded = load_project_state(record)

    assert saved.revision == 1
    assert loaded.pipeline.applied_style_id == "sr-x-native-video-card"
    assert loaded.pipeline.short_captions == {"Hook": str(tmp_path / "hook.ass")}
    assert loaded.pipeline.pcm_digest == "abc"
    assert loaded.pipeline.discard_sentence_ids == [7]
    assert loaded.pipeline.checkpoints[-1].step == "transcribe"

    restored = context_from_pipeline(
        PipelineContext(
            source=tmp_path,
            output=Path(record.output),
            work=Path(record.output) / "work",
            exports=Path(record.output) / "exports",
            state=loaded,
        ),
        loaded,
        project_id=record.project_id,
    )
    assert restored.selected_shorts[0].title == "Hook"
    assert restored.short_captions["Hook"].endswith("hook.ass")


def test_time_map_is_bidirectional_and_handles_cut_gaps(tmp_path: Path) -> None:
    state = _state(tmp_path).model_copy(
        update={
            "video_segments": [
                VideoSegment(
                    clip_id="v1",
                    source_id="primary",
                    source_in_frame=0,
                    source_out_frame=300,
                    timeline_in_frame=0,
                    timeline_out_frame=300,
                ),
                VideoSegment(
                    clip_id="v2",
                    source_id="primary",
                    source_in_frame=600,
                    source_out_frame=900,
                    timeline_in_frame=300,
                    timeline_out_frame=600,
                ),
            ]
        }
    )
    assert source_to_timeline_sec(state, 0) == 0
    assert source_to_timeline_sec(state, 5) == 5
    assert source_to_timeline_sec(state, 20) == 10
    assert source_to_timeline_sec(state, 25) == 15
    assert timeline_to_source_sec(state, 10) == 20
    assert timeline_to_source_sec(state, 15) == 25
    assert source_range_to_timeline(state, 0, 30) == [(0, 10), (10, 20)]
    with pytest.raises(TimeMapError):
        source_to_timeline_sec(state, 15)


def test_revisions_roundtrip(tmp_path: Path) -> None:
    state = _state(tmp_path)
    first = create_snapshot(tmp_path, state, reason="before edit")
    changed = state.model_copy(update={"style_id": "sr-x"})
    second = create_snapshot(tmp_path, changed, reason="after edit")
    assert first == "rev_001"
    assert second == "rev_002"
    items = list_snapshots(tmp_path)
    assert [item["revision_id"] for item in items] == ["rev_002", "rev_001"]
    assert load_snapshot(tmp_path, first).style_id == ""


def test_beatmap_remove_ranges_dry_run_force_and_undo(tmp_path: Path) -> None:
    state = _state(tmp_path)
    report_state, report, _ = apply_beatmap(
        state,
        tmp_path,
        {"remove_ranges": [{"start_sec": 10, "end_sec": 20}]},
        dry_run=True,
        apply_cuts=True,
    )
    assert state.video_segments[0].timeline_out_frame == 1800
    assert report_state.video_segments[-1].timeline_out_frame == 1500
    assert report.after_duration_sec == 50
    assert report.delta_pct == pytest.approx(-16.667, abs=0.01)
    with pytest.raises(BeatmapError) as info:
        apply_beatmap(
            state,
            tmp_path,
            {"remove_ranges": [{"start_sec": 10, "end_sec": 50}]},
            apply_cuts=True,
        )
    assert "force" in str(info.value)
    updated, report, _ = apply_beatmap(
        state,
        tmp_path,
        {"remove_ranges": [{"start_sec": 10, "end_sec": 50}]},
        force=True,
        apply_cuts=True,
    )
    assert report.after_duration_sec == 20
    assert updated.video_segments[-1].timeline_out_frame == 600
    assert updated.pipeline.time_map


def test_chain_job_persists_context_between_steps(tmp_path: Path) -> None:
    calls: list[str] = []

    class FirstStep(BaseStep):
        type = "test.wave_a_first"
        title = "First"
        params_model = EmptyParams

        def run(self, context, params: BaseModel, io: StepIO) -> None:
            calls.append("first")
            context.metadata["first"] = True
            context.transcript = []
            io.report(100, "first done")

    class SecondStep(BaseStep):
        type = "test.wave_a_second"
        title = "Second"
        params_model = EmptyParams

        def run(self, context, params: BaseModel, io: StepIO) -> None:
            calls.append("second")
            assert context.metadata.get("first") is True
            io.report(100, "second done")

    for step in (FirstStep, SecondStep):
        with contextlib.suppress(ValueError):
            register_step(step)

    from videoflow.application.jobs import JobManager

    record, _ = init_project(name="Chain", output=tmp_path / "chain")
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    job = manager.start(
        Path(record.output),
        Path(record.output),
        {
            "mode": "run",
            "project_id": record.project_id,
            "steps": ["test.wave_a_first", "test.wave_a_second"],
            "resume": True,
        },
        queue=True,
        project_id=record.project_id,
    )
    deadline = time.time() + 5
    while time.time() < deadline and manager.get(str(job.job_id)).status not in {
        "succeeded",
        "failed",
        "cancelled",
    }:
        time.sleep(0.01)
    finished = manager.get(str(job.job_id))
    assert finished.status == "succeeded", finished.error
    assert calls == ["first", "second"]
    loaded = load_project_state(get_project(record.project_id))
    assert [item.step for item in loaded.pipeline.checkpoints] == [
        "test.wave_a_first",
        "test.wave_a_second",
    ]


def test_project_lifecycle_and_revision_tools(tmp_path: Path) -> None:
    from videoflow.application.projects import (
        archive_project,
        clone_project,
        delete_project,
        project_disk_size,
    )

    record, state = init_project(name="Lifecycle", output=tmp_path / "lifecycle")
    updated = state.model_copy(update={"style_id": "sr-x"})
    saved = save_project_state(
        record,
        updated,
        snapshot=True,
        snapshot_reason="test edit",
    )
    assert saved.revision == 2
    assert list_snapshots(record.output)[0]["reason"] == "test edit"
    assert project_disk_size(record) > 0

    archived = archive_project(record)
    assert archived.status == "archived"
    archive_project(archived, archived=False)

    clone, clone_state = clone_project(record)
    assert clone.project_id != record.project_id
    assert str(clone_state.project_id) == clone.project_id
    assert Path(clone.output).is_dir()
    delete_project(clone, force=True)
    assert not Path(clone.output).exists()

    from videoflow.application.jobs import JobManager
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(
            manager=manager,
        ),
    )
    history = tools["vf_project"](action="history", project_id=record.project_id)
    assert history["ok"] is True
    assert history["revisions"]
    undone = tools["vf_project"](action="undo", project_id=record.project_id)
    assert undone["ok"] is True
    assert load_project_state(get_project(record.project_id)).style_id == ""

    listing = tools["vf_project"](action="list", include_archived=True)
    assert any(item["project_id"] == record.project_id for item in listing["projects"])


def test_vf_job_lists_and_cancels_shared_store(tmp_path: Path) -> None:
    from videoflow.application import database
    from videoflow.application.jobs import JobManager
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    database.migrate_home()
    database.upsert_job(
        "job-wave-a",
        {
            "job_id": "job-wave-a",
            "project_id": "project-wave-a",
            "status": "running",
            "progress": 40,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:01+00:00",
        },
    )
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager),
    )
    listed = tools["vf_job"](action="list", project_id="project-wave-a")
    assert listed["ok"] is True
    assert listed["jobs"][0]["job_id"] == "job-wave-a"
    cancelled = tools["vf_job"](action="cancel", job_id="job-wave-a", force=True)
    assert cancelled["ok"] is True
    assert database.job_cancel_requested("job-wave-a") is True
    status = tools["vf_job"](action="status", job_id="job-wave-a")
    assert status["job"]["status"] == "cancelled"


def test_vf_timeline_dry_run_and_time_basis(tmp_path: Path) -> None:
    from videoflow.application.jobs import JobManager
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    record, _ = init_project(name="Timeline", output=tmp_path / "timeline")
    state = _state(tmp_path).model_copy(update={"project_id": UUID(record.project_id)})
    save_project_state(record, state, bump_revision=False)
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager),
    )
    dry = tools["vf_timeline"](
        action="apply_beatmap",
        project_id=record.project_id,
        remove_ranges=[{"start_sec": 1.0, "end_sec": 2.0}],
        dry_run=True,
    )
    assert dry["ok"] is True
    assert dry["dry_run"] is True
    assert dry["report"]["after_duration_sec"] == 59
    assert load_project_state(get_project(record.project_id)).revision == 1


def test_vf_run_tool_executes_linear_chain(tmp_path: Path) -> None:
    from videoflow.application.jobs import JobManager
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    class RunStep(BaseStep):
        type = "test.wave_a_run_tool"
        title = "Run tool"
        params_model = EmptyParams

        def run(self, context, params: BaseModel, io: StepIO) -> None:
            context.metadata["run_tool"] = True
            io.report(100, "done")

    with contextlib.suppress(ValueError):
        register_step(RunStep)
    record, _ = init_project(name="Run", output=tmp_path / "run")
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager),
    )
    response = tools["vf_run"](
        project_id=record.project_id,
        steps=["test.wave_a_run_tool"],
        wait=True,
        timeout_sec=10,
    )
    assert response["ok"] is True
    assert response["wait"]["ok"] is True
    loaded = load_project_state(get_project(record.project_id))
    assert loaded.pipeline.metadata["run_tool"] is True
