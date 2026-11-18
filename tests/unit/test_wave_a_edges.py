from __future__ import annotations

import contextlib
import json
from pathlib import Path
from uuid import UUID

import pytest

from videoflow.application import database
from videoflow.application.beatmap import BeatmapError, apply_beatmap
from videoflow.application.jobs import JobManager
from videoflow.application.pipeline_state import (
    context_from_pipeline,
    update_pipeline_from_context,
)
from videoflow.application.projects import (
    clone_project,
    delete_project,
    get_project,
    init_project,
    list_projects,
    load_project_state,
    project_disk_size,
    save_project_state,
)
from videoflow.application.revisions import (
    create_snapshot,
    latest_snapshot,
    list_snapshots,
    load_snapshot,
)
from videoflow.application.time_map import (
    TimeMapError,
    build_time_map,
    source_range_to_timeline,
    source_to_timeline_sec,
    timeline_to_source_sec,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ProjectStateError
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment


def _media(tmp_path: Path, *, name: str = "source.mp4") -> MediaInfo:
    source = tmp_path / name
    source.write_bytes(b"x")
    return MediaInfo(
        source_path=str(source),
        duration_frames=1800,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )


def _state(tmp_path: Path) -> ProjectState:
    media = _media(tmp_path)
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


def test_pipeline_state_edge_cases(tmp_path: Path) -> None:
    state = ProjectState()
    context = PipelineContext(
        source=tmp_path,
        output=tmp_path,
        work=tmp_path,
        exports=tmp_path,
    )

    class CustomClip:
        def __init__(self) -> None:
            self.title = "custom"

    class BadJson:
        def __str__(self) -> str:
            raise RuntimeError("cannot stringify")

    context.selected_shorts = [CustomClip(), {"title": "dict"}, None]
    context.metadata["bad"] = BadJson()
    updated = update_pipeline_from_context(state, context, step="")
    assert updated.pipeline.metadata == {}
    assert len(updated.pipeline.selected_shorts) == 1
    assert updated.pipeline.checkpoints == []

    context.selected_shorts = []
    context.metadata["large"] = "x" * 2_100_000
    updated = update_pipeline_from_context(state, context, step="")
    assert updated.pipeline.metadata == {}

    context.metadata = {}
    context.artifacts = {"a": "", "b": str(tmp_path / "missing")}
    updated = update_pipeline_from_context(state, context, step="")
    assert updated.pipeline.artifacts == {"b": str(tmp_path / "missing")}


def test_context_from_pipeline_rebuilds_time_map_and_skips_bad_shorts(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state = state.model_copy(
        update={
            "pipeline": state.pipeline.model_copy(update={"selected_shorts": [{"title": "bad"}]})
        }
    )
    base = PipelineContext(
        source=tmp_path,
        output=tmp_path,
        work=tmp_path,
        exports=tmp_path,
        state=state,
    )
    restored = context_from_pipeline(base, state, project_id="p", job_id="j")
    assert restored.state is not None
    assert restored.state.pipeline.time_map
    assert restored.metadata["project_id"] == "p"
    assert restored.selected_shorts[0].title == "bad"


def test_time_map_edges(tmp_path: Path) -> None:
    empty = ProjectState()
    assert build_time_map(empty) == []
    with pytest.raises(TimeMapError):
        source_to_timeline_sec(empty, 0)
    with pytest.raises(TimeMapError):
        timeline_to_source_sec(empty, 0)
    with pytest.raises(TimeMapError):
        source_range_to_timeline(empty, 0, 1)

    state = _state(tmp_path)
    with pytest.raises(TimeMapError):
        source_to_timeline_sec(state, 1.0, source_id="missing")
    with pytest.raises(TimeMapError):
        source_range_to_timeline(state, 20, 10)
    with pytest.raises(TimeMapError):
        source_range_to_timeline(state, 100, 200)

    second = _media(tmp_path, name="second.mp4")
    sources = {"primary": state.media_info, "second": second}
    dual = state.model_copy(update={"sources": sources, "primary_source_id": "primary"})
    dual = dual.model_copy(
        update={
            "video_segments": [
                *state.video_segments,
                VideoSegment(
                    clip_id="v2",
                    source_id="second",
                    source_in_frame=0,
                    source_out_frame=300,
                    timeline_in_frame=1800,
                    timeline_out_frame=2100,
                ),
            ]
        }
    )
    restored = context_from_pipeline(
        PipelineContext(
            source=tmp_path,
            output=tmp_path,
            work=tmp_path,
            exports=tmp_path,
            state=dual,
        ),
        dual,
    )
    assert len(restored.state.pipeline.time_map) == 2  # type: ignore[union-attr]


def test_revision_error_paths(tmp_path: Path) -> None:
    with pytest.raises(ProjectStateError):
        load_snapshot(tmp_path, "../bad")
    with pytest.raises(ProjectStateError):
        latest_snapshot(tmp_path)
    first = create_snapshot(tmp_path, _state(tmp_path), reason="one")
    assert load_snapshot(tmp_path, first).style_id == ""
    assert list_snapshots(tmp_path)[0]["revision_id"] == first
    (tmp_path / "history" / "rev_999.meta.json").write_text("not json", encoding="utf-8")
    assert all(item["revision_id"] != "rev_999" for item in list_snapshots(tmp_path))
    (tmp_path / "history" / "rev_001.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ProjectStateError):
        load_snapshot(tmp_path, first)


def test_beatmap_keep_ranges_source_basis_and_captions_dry_run(tmp_path: Path) -> None:
    state = _state(tmp_path)
    updated, report, sidecar = apply_beatmap(
        state,
        tmp_path,
        {
            "time_basis": "source",
            "keep_ranges": [{"start_sec": 0, "end_sec": 10}],
            "captions": [{"text": "hello", "start_frame": 0, "end_frame": 30}],
        },
        dry_run=True,
        force=True,
    )
    assert updated.video_segments[-1].timeline_out_frame == 300
    assert report.captions == 1
    assert "captions_file" not in sidecar
    assert report.dry_run is True

    with pytest.raises(BeatmapError):
        apply_beatmap(
            state,
            tmp_path,
            {"keep_ranges": [{"start_sec": 0, "end_sec": 10}]},
            time_basis="timeline",
            force=False,
        )

    _, empty_report, _ = apply_beatmap(
        state,
        tmp_path,
        {"remove_ranges": [{"start_sec": 0, "end_sec": 60}]},
        force=True,
    )
    assert empty_report.after_duration_sec == 0

    _, warn_report, _ = apply_beatmap(
        state,
        tmp_path,
        {"cuts": [{"start_frame": 0, "end_frame": 300}]},
        force=True,
    )
    assert any("deprecated" in item for item in warn_report.warnings)


def test_project_lifecycle_and_database_edges(tmp_path: Path) -> None:
    record, state = init_project(name="Edges", output=tmp_path / "edges")
    assert project_disk_size(record.model_copy(update={"output": str(tmp_path / "missing")})) == 0
    with pytest.raises(ProjectStateError):
        delete_project(record)
    with pytest.raises(ProjectStateError):
        clone_project(record, output=record.output)
    clone_dir = tmp_path / "clone-nonempty"
    clone_dir.mkdir()
    (clone_dir / "x").write_text("x", encoding="utf-8")
    with pytest.raises(ProjectStateError):
        clone_project(record, output=str(clone_dir))
    assert any(item.project_id == record.project_id for item in list_projects())

    database.upsert_job("edge-job", {"job_id": "edge-job", "status": "queued"})
    assert database.request_job_cancel("missing-job") is None
    assert database.job_cancel_requested("missing-job") is False
    assert database.request_job_cancel("edge-job", force=True) is not None
    assert database.job_cancel_requested("edge-job") is True
    assert database.list_jobs(status="cancelled", job_id="edge-job", limit=1)
    database.delete_project(record.project_id)
    assert all(item.project_id != record.project_id for item in list_projects())


def test_job_chain_through_resume_and_failure(tmp_path: Path) -> None:
    from pydantic import BaseModel

    from videoflow.steps.base import BaseStep, EmptyParams, StepIO
    from videoflow.steps.registry import register_step

    class EdgeFirst(BaseStep):
        type = "test.wave_a_edge_first"
        title = "Edge first"
        params_model = EmptyParams

        def run(self, context, params: BaseModel, io: StepIO) -> None:
            context.metadata["edge_first"] = True

    class EdgeSecond(BaseStep):
        type = "test.wave_a_edge_second"
        title = "Edge second"
        params_model = EmptyParams

        def run(self, context, params: BaseModel, io: StepIO) -> None:
            context.metadata["edge_second"] = True

    for step in (EdgeFirst, EdgeSecond):
        with contextlib.suppress(ValueError):
            register_step(step)
    record, _ = init_project(name="Chain edges", output=tmp_path / "chain-edges")
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    job = manager.start(
        Path(record.output),
        Path(record.output),
        {
            "mode": "run",
            "project_id": record.project_id,
            "steps": ["test.wave_a_edge_first", "test.wave_a_edge_second"],
            "resume": True,
            "through": "test.wave_a_edge_first",
        },
        queue=True,
        project_id=record.project_id,
    )
    deadline = __import__("time").time() + 5
    while __import__("time").time() < deadline and manager.get(str(job.job_id)).status not in {
        "succeeded",
        "failed",
    }:
        __import__("time").sleep(0.01)
    assert manager.get(str(job.job_id)).status == "succeeded"
    loaded = load_project_state(get_project(record.project_id))
    assert [item.step for item in loaded.pipeline.checkpoints] == ["test.wave_a_edge_first"]

    second = manager.start(
        Path(record.output),
        Path(record.output),
        {
            "mode": "run",
            "project_id": record.project_id,
            "steps": ["test.wave_a_edge_first", "test.wave_a_edge_second"],
            "resume": True,
        },
        queue=True,
        project_id=record.project_id,
    )
    deadline = __import__("time").time() + 5
    while __import__("time").time() < deadline and manager.get(str(second.job_id)).status not in {
        "succeeded",
        "failed",
    }:
        __import__("time").sleep(0.01)
    assert manager.get(str(second.job_id)).status == "succeeded"
    loaded = load_project_state(get_project(record.project_id))
    assert [item.step for item in loaded.pipeline.checkpoints][-1] == "test.wave_a_edge_second"


def test_vf_run_and_jobs_error_paths(tmp_path: Path) -> None:
    from videoflow.engine.batch import BatchManager
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    record, _ = init_project(name="Errors", output=tmp_path / "errors")
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager, batch_manager=BatchManager(manager)),
    )
    assert tools["vf_run"](project_id="missing", steps=["ingest"])["ok"] is False
    assert tools["vf_run"](project_id=record.project_id, steps=[])["ok"] is False
    assert tools["vf_run"](project_id=record.project_id, steps=["missing.step"])["ok"] is False
    assert (
        tools["vf_run"](
            project_id=record.project_id,
            steps=["ingest"],
            through="transcribe",
        )["ok"]
        is False
    )
    assert tools["vf_jobs"](action="status", job_id="missing")["ok"] is False
    assert tools["vf_jobs"](action="cancel", job_id="missing")["ok"] is False
    assert tools["vf_jobs"](action="unknown")["ok"] is False
    assert tools["vf_jobs"](action="list", limit=0)["ok"] is True


def test_vf_timeline_and_project_error_paths(tmp_path: Path) -> None:
    from videoflow.engine.batch import BatchManager
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    record, _ = init_project(name="Timeline errors", output=tmp_path / "timeline-errors")
    state = _state(tmp_path).model_copy(update={"project_id": UUID(record.project_id)})
    save_project_state(record, state, bump_revision=False)
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager, batch_manager=BatchManager(manager)),
    )
    assert (
        tools["vf_timeline"](
            action="apply_beatmap",
            project_id=record.project_id,
        )["ok"]
        is False
    )
    assert (
        tools["vf_timeline"](
            action="apply_beatmap",
            project_id=record.project_id,
            remove_ranges=[{"start_sec": 0, "end_sec": 1}],
            time_basis="bad",
        )["ok"]
        is False
    )
    assert (
        tools["vf_timeline"](
            action="edit",
            project_id=record.project_id,
            clip_id="v1",
            time_basis="bad",
        )["ok"]
        is False
    )
    assert (
        tools["vf_timeline"](
            action="edit",
            project_id=record.project_id,
            clip_id="v1",
            time_basis="source",
            start_sec=100,
        )["ok"]
        is False
    )
    assert tools["vf_project"](action="history", project_id="missing")["ok"] is False
    assert tools["vf_project"](action="restore", project_id=record.project_id)["ok"] is False
    assert (
        tools["vf_project"](
            action="delete",
            project_id=record.project_id,
            force=False,
        )["ok"]
        is False
    )


def test_pipeline_json_size_guard(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application import pipeline_state

    monkeypatch.setattr(pipeline_state, "_MAX_JSON_BYTES", 10)
    assert pipeline_state._json_safe({"long": "x" * 20}) is None
    state = ProjectState()
    context = PipelineContext(
        source=tmp_path,
        output=tmp_path,
        work=tmp_path,
        exports=tmp_path,
    )
    updated = update_pipeline_from_context(state, context, step="")
    assert json.loads(updated.model_dump_json())["pipeline"]["metadata"] == {}


def test_beatmap_overlay_layouts_and_helpers(tmp_path: Path) -> None:
    from videoflow.application.beatmap import (
        BeatmapCut,
        BeatmapOverlay,
        BeatmapRange,
        _complement,
        _intersect,
        _overlay_from,
        _ranges_to_frames,
        _seconds_to_frames,
    )

    asset = tmp_path / "overlay.png"
    asset.write_bytes(b"x")
    layouts = [
        "pip_top_right",
        "split_screen",
        "cutout_overlay",
        "ken_burns",
        "transformative_crop",
    ]
    for index, layout in enumerate(layouts):
        overlay = _overlay_from(
            BeatmapOverlay(path=str(asset), start_frame=0, duration_frames=30, layout=layout),
            index,
            asset,
        )
        assert overlay.layout == layout
    state = _state(tmp_path)
    assert _seconds_to_frames(state, 1.0) == (30, 30)
    assert _seconds_to_frames(ProjectState(), 1.0) == (0, 0)
    assert (
        _ranges_to_frames(ProjectState(), [BeatmapRange(start_sec=0, end_sec=1)], "timeline") == []
    )
    assert _intersect(
        [BeatmapCut(start_frame=0, end_frame=60)],
        [BeatmapCut(start_frame=30, end_frame=90)],
    ) == [BeatmapCut(start_frame=30, end_frame=60)]
    assert _complement([], 30) == [BeatmapCut(start_frame=0, end_frame=30)]


def test_beatmap_keep_and_remove_intersect(tmp_path: Path) -> None:
    state = _state(tmp_path)
    updated, report, _ = apply_beatmap(
        state,
        tmp_path,
        {
            "keep_ranges": [{"start_sec": 0, "end_sec": 30}],
            "remove_ranges": [{"start_sec": 10, "end_sec": 20}],
        },
        force=True,
    )
    assert report.after_duration_sec == 20
    assert updated.video_segments[-1].timeline_out_frame == 600


def test_revision_pruning(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application import revisions

    monkeypatch.setattr(revisions, "MAX_SNAPSHOTS", 1)
    create_snapshot(tmp_path, _state(tmp_path), reason="old")
    create_snapshot(tmp_path, _state(tmp_path), reason="new")
    items = list_snapshots(tmp_path)
    assert [item["reason"] for item in items] == ["new"]
    assert not (tmp_path / "history" / "rev_001.json").exists()


def test_init_existing_project_and_corrupt_state(tmp_path: Path) -> None:
    from videoflow.application.projects import init_project

    record, _ = init_project(name="Existing", output=tmp_path / "existing")
    again, state = init_project(
        name="Existing",
        output=tmp_path / "existing",
        channel_id="rafael-tech",
        style_id="canal-rafael-tech",
    )
    assert again.project_id == record.project_id
    assert state.style_id == "canal-rafael-tech"

    bad = tmp_path / "corrupt"
    bad.mkdir()
    (bad / "project_state.json").write_text("{not json", encoding="utf-8")
    recovered, recovered_state = init_project(name="Corrupt", output=bad)
    assert recovered.project_id
    assert recovered_state.schema_version == 3


def test_job_chain_failure_and_skipped_through(tmp_path: Path) -> None:
    from pydantic import BaseModel

    from videoflow.steps.base import BaseStep, EmptyParams, StepIO
    from videoflow.steps.registry import register_step

    class EdgeFail(BaseStep):
        type = "test.wave_a_edge_fail"
        title = "Edge fail"
        params_model = EmptyParams

        def run(self, context, params: BaseModel, io: StepIO) -> None:
            raise RuntimeError("boom")

    with contextlib.suppress(ValueError):
        register_step(EdgeFail)
    record, _ = init_project(name="Failure", output=tmp_path / "failure")
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    job = manager.start(
        Path(record.output),
        Path(record.output),
        {
            "mode": "run",
            "project_id": record.project_id,
            "steps": ["test.wave_a_edge_fail"],
            "resume": True,
        },
        queue=True,
        project_id=record.project_id,
    )
    deadline = __import__("time").time() + 5
    while __import__("time").time() < deadline and manager.get(str(job.job_id)).status not in {
        "succeeded",
        "failed",
    }:
        __import__("time").sleep(0.01)
    assert manager.get(str(job.job_id)).status == "failed"
    loaded = load_project_state(get_project(record.project_id))
    assert loaded.pipeline.checkpoints[-1].status == "failed"

    # Resume a chain whose first step is already complete and through points at it.
    from videoflow.application import jobs as jobs_module

    context = jobs_module.JobManager(store_dir=tmp_path / "jobs2", load_store=False)
    assert context is not None


def test_queue_cancel_flag(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application import queue_claim

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "queue-home"))
    database.migrate_home()
    database.upsert_job("queue-edge", {"job_id": "queue-edge", "status": "queued"})
    assert queue_claim.cancel_requested("queue-edge") is False
    database.request_job_cancel("queue-edge", force=True)
    assert queue_claim.cancel_requested("queue-edge") is True
    assert queue_claim.claim_next("worker") is None


def test_project_tool_archive_clone_delete(tmp_path: Path) -> None:
    from videoflow.engine.batch import BatchManager
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    record, _ = init_project(name="Tool lifecycle", output=tmp_path / "tool-lifecycle")
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager, batch_manager=BatchManager(manager)),
    )
    archived = tools["vf_project"](action="archive", project_id=record.project_id)
    assert archived["project"]["status"] == "archived"
    restored = tools["vf_project"](action="unarchive", project_id=record.project_id)
    assert restored["project"]["status"] == "active"
    clone = tools["vf_project"](
        action="clone",
        project_id=record.project_id,
        output=str(tmp_path / "tool-clone"),
        name="Clone",
    )
    assert clone["ok"] is True
    deleted = tools["vf_project"](
        action="delete",
        project_id=clone["project"]["project_id"],
        force=True,
    )
    assert deleted["ok"] is True
    listed = tools["vf_project"](action="list")
    assert listed["ok"] is True


def test_run_tool_accepts_string_and_timeline_applies_snapshot(tmp_path: Path) -> None:
    from videoflow.engine.batch import BatchManager
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    record, _ = init_project(name="String run", output=tmp_path / "string-run")
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager, batch_manager=BatchManager(manager)),
    )
    response = tools["vf_run"](
        project_id=record.project_id,
        steps="ingest",
        wait=False,
    )
    assert response["ok"] is True

    timeline_record, _ = init_project(name="Timeline apply", output=tmp_path / "timeline-apply")
    state = _state(tmp_path).model_copy(update={"project_id": UUID(timeline_record.project_id)})
    save_project_state(timeline_record, state, bump_revision=False)
    applied = tools["vf_timeline"](
        action="apply_beatmap",
        project_id=timeline_record.project_id,
        remove_ranges=[{"start_sec": 0, "end_sec": 1}],
        force=True,
    )
    assert applied["ok"] is True
    assert applied["revision"] == 2
    assert list_snapshots(timeline_record.output)


def test_beatmap_graphics_transitions_zoom_branches(tmp_path: Path) -> None:
    from videoflow.application.beatmap import BeatmapError

    state = _state(tmp_path)
    asset = tmp_path / "missing.png"
    asset.write_bytes(b"x")
    _, report, _ = apply_beatmap(
        state,
        tmp_path,
        {
            "graphics": [
                {
                    "path": str(asset),
                    "start_frame": 0,
                    "duration_frames": 30,
                }
            ],
            "transitions": [
                {
                    "clip_id": "v1",
                    "type": "crossfade",
                    "duration_frames": 4,
                    "linked_sfx": "",
                }
            ],
            "zoom_keyframes": [{"clip_id": "v1", "keyframes": []}],
        },
    )
    assert report.graphics == 1
    assert report.transitions == 1

    with pytest.raises(BeatmapError):
        apply_beatmap(
            state,
            tmp_path,
            {"transitions": [{"clip_id": "missing", "type": "crossfade"}]},
        )
    with pytest.raises(BeatmapError):
        apply_beatmap(
            state,
            tmp_path,
            {
                "graphics": [
                    {"path": str(tmp_path / "absent.png"), "start_frame": 0, "duration_frames": 30}
                ]
            },
        )


def test_project_tool_status_filter_and_workflow_branch(tmp_path: Path) -> None:
    from videoflow.application.projects import archive_project
    from videoflow.engine.batch import BatchManager
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    record, _ = init_project(name="Filter", output=tmp_path / "filter")
    archive_project(record)
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager, batch_manager=BatchManager(manager)),
    )
    active_only = tools["vf_project"](action="list")
    assert all(item["status"] != "archived" for item in active_only["projects"])
    archived = tools["vf_project"](action="list", status="archived", include_archived=True)
    assert any(item["project_id"] == record.project_id for item in archived["projects"])
    workflow = tools["vf_run"](project_id=record.project_id, steps="clone-style", wait=False)
    assert workflow["ok"] is False


def test_time_map_seconds_and_zoom_with_untouched_clip(tmp_path: Path) -> None:
    from videoflow.application.time_map import _seconds

    assert _seconds(-1) >= 0
    state = _state(tmp_path)
    second = VideoSegment(
        clip_id="v2",
        source_id="primary",
        source_in_frame=300,
        source_out_frame=600,
        timeline_in_frame=1800,
        timeline_out_frame=2100,
    )
    state = state.model_copy(update={"video_segments": [*state.video_segments, second]})
    _, report, _ = apply_beatmap(
        state,
        tmp_path,
        {"zoom_keyframes": [{"clip_id": "v1", "keyframes": []}]},
        force=True,
    )
    assert report.zooms == 1


def test_revision_write_failure_is_cleaned(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application import revisions

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(revisions.os, "replace", fail)
    with pytest.raises(OSError):
        create_snapshot(tmp_path, _state(tmp_path), reason="fail")
    assert not list((tmp_path / "history").glob("*.tmp"))


def test_database_error_handlers(monkeypatch) -> None:
    import sqlite3

    def broken():
        raise sqlite3.OperationalError("closed")

    monkeypatch.setattr(database, "connect", broken)
    database.upsert_job("x", {"job_id": "x"})
    assert database.get_project("x") is None
    assert isinstance(database.list_projects(), list)
    assert isinstance(database.list_jobs(), list)
    assert database.request_job_cancel("x") is None
    assert database.job_cancel_requested("x") is False
    database.delete_job("x")
    database.delete_project("x")
