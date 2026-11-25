"""v4.7.0 MCP contracts: real waits, license unblocking, and full pagination."""

from __future__ import annotations

import json
from pathlib import Path

from videoflow.application.beatmap import apply_beatmap
from videoflow.application.jobs import Job
from videoflow.application.projects import init_project, save_project_state
from videoflow.domain.scenes import SceneEntry, ScenesManifest
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    PipelineState,
    ProjectState,
    Sentence,
    VideoSegment,
    WordTiming,
)
from videoflow.domains.media.ledger import is_asset_approved, license_blockers
from videoflow.mcp_server.context import ToolContext
from videoflow.mcp_server.core_tools import register_core_tools

RATE = 48_000


class Manager:
    def __init__(self, job: Job):
        self.job = job

    def start(self, source, output, options, **kwargs):
        self.job.source = Path(source)
        self.job.output = Path(output)
        self.job.options = dict(options)
        self.job.status = "queued"
        return self.job

    def get(self, job_id):
        self.job.status = "succeeded"
        self.job.result = {"ok": True, "finished": True}
        return self.job

    def list(self, **kwargs):
        return [self.job]

    def cancel(self, job_id, *, force: bool = False):
        return self.job

    def update_result(self, job_id, result):
        self.job.result = result


def _tools(tmp_path: Path, monkeypatch, state: ProjectState | None = None):
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    record, project_state = init_project(
        project_id="demo",
        name="Demo",
        output=tmp_path / "out",
    )
    if state is not None:
        project_state = state
    save_project_state(record, project_state, bump_revision=False)
    (Path(record.output) / "exports").mkdir(parents=True, exist_ok=True)
    job = Job(
        source=source,
        output=Path(record.output),
        options={"origin": "mcp"},
        project_id=record.project_id,
        status="queued",
    )
    tools: dict[str, object] = {}

    def register(func):
        tools[func.__name__] = func
        return func

    register_core_tools(register, ToolContext(manager=Manager(job)))  # type: ignore[arg-type]
    return tools, record, job


def _media(frames: int = 30) -> MediaInfo:
    return MediaInfo(
        source_path="/tmp/source.mp4",
        duration_frames=frames,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=RATE,
    )


def _transcript(count: int) -> list[Sentence]:
    return [
        Sentence(
            id=index,
            start_sample=index * RATE,
            end_sample=(index + 1) * RATE,
            text=f"frase {index}",
            words=[
                WordTiming(
                    word=f"frase{index}",
                    start_sample=index * RATE,
                    end_sample=(index + 1) * RATE,
                    probability=0.9,
                )
            ],
        )
        for index in range(count)
    ]


def _timeline_state(count: int = 104) -> ProjectState:
    media = _media(frames=count * 30)
    return ProjectState(
        media_info=media,
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_in_frame=0,
                source_out_frame=count * 30,
                timeline_in_frame=0,
                timeline_out_frame=count * 30,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="a1",
                source_in_sample=0,
                source_out_sample=count * RATE,
                timeline_in_sample=0,
                timeline_out_sample=count * RATE,
            )
        ],
        transcript=_transcript(count),
    )


def test_vf_run_wait_returns_the_terminal_job(tmp_path: Path, monkeypatch) -> None:
    tools, record, _job = _tools(tmp_path, monkeypatch)
    result = tools["vf_run"](
        project_id=record.project_id,
        steps=["ingest"],
        wait=True,
    )
    assert result["ok"] is True
    assert result["job"]["status"] == "succeeded"
    assert result["wait"]["job"]["status"] == "succeeded"


def test_vf_transcript_paginates_all_104_sentences(
    tmp_path: Path, monkeypatch
) -> None:
    tools, record, _job = _tools(tmp_path, monkeypatch, _timeline_state(104))
    seen: list[int] = []
    cursor = 0
    while cursor is not None:
        payload = tools["vf_transcript"](
            action="query",
            project_id=record.project_id,
            limit=30,
            cursor=cursor,
        )
        assert payload["ok"] is True
        seen.extend(item["id"] for item in payload["sentences"])
        cursor = payload["next_cursor"]
    assert len(seen) == 104
    assert len(set(seen)) == 104
    assert seen == list(range(104))


def test_vf_transcript_editorial_map_returns_scene_and_speech(
    tmp_path: Path, monkeypatch
) -> None:
    state = _timeline_state(40)
    state = state.model_copy(
        update={
            "pipeline": PipelineState(
                metadata={
                    "scenes_manifest": ScenesManifest(
                        video_id="demo",
                        resolution={"w": 320, "h": 240},
                        fps_num=30,
                        fps_den=1,
                        scenes=[
                            SceneEntry(
                                scene_id="SC_0001",
                                start_sample=0,
                                end_sample=40 * RATE,
                                start_sec=0.0,
                                end_sec=40.0,
                                layout_type="TALKING_HEAD",
                                keyframe_path="/tmp/keyframe.jpg",
                            )
                        ],
                    ).model_dump(mode="json")
                }
            )
        }
    )
    tools, record, _job = _tools(tmp_path, monkeypatch, state)
    payload = tools["vf_transcript"](
        action="editorial_map",
        project_id=record.project_id,
    )
    assert payload["ok"] is True
    assert payload["count"] >= 2
    assert payload["blocks"]
    first = payload["blocks"][0]
    assert {"edited_start_sec", "edited_end_sec", "text", "layout_type"} <= set(first)
    assert first["layout_type"] == "TALKING_HEAD"
    assert first["protected_from_broll"] is False
    assert first["keyframe_path"] == "/tmp/keyframe.jpg"


def test_vf_timeline_time_map_and_page_size(tmp_path: Path, monkeypatch) -> None:
    tools, record, _job = _tools(tmp_path, monkeypatch, _timeline_state(40))
    payload = tools["vf_timeline"](action="time_map", project_id=record.project_id)
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["time_map"][0][0] == 0.0
    assert payload["time_map"][0][2] == 0.0


def test_approve_license_finds_a_disk_asset_and_unblocks_the_beatmap(
    tmp_path: Path, monkeypatch
) -> None:
    tools, record, _job = _tools(tmp_path, monkeypatch, _timeline_state(2))
    output = Path(record.output)
    asset = output / "assets" / "broll" / "clip.mp4"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(b"video")
    sidecar = asset.with_name(f"{asset.name}.meta.json")
    sidecar.write_text(
        json.dumps({"asset_id": "broll-test", "sha256": "abc123"}),
        encoding="utf-8",
    )
    approved = tools["vf_media"](
        action="approve_license",
        project_id=record.project_id,
        asset_ids=["broll-test"],
        license="cc0",
        attribution="Test",
    )
    assert approved["ok"] is True
    assert approved["changed"] == ["broll-test"]
    assert is_asset_approved(output, "broll-test", path=str(asset)) is True
    assert license_blockers(output) == []

    state = _timeline_state(2)
    updated, report, _sidecar = apply_beatmap(
        state,
        output,
        {
            "revision": state.revision,
            "time_basis": "timeline",
            "overlays": [
                {
                    "path": "assets/broll/clip.mp4",
                    "start_frame": 0,
                    "duration_frames": 15,
                    "kind": "video",
                }
            ],
        },
        time_basis="timeline",
    )
    assert report.ok is True
    assert not any("license-blocked" in item for item in report.conflicts)
    assert updated.overlays


def test_vf_export_accepts_mp4_and_skip_qa_aliases(
    tmp_path: Path, monkeypatch
) -> None:
    tools, record, _job = _tools(tmp_path, monkeypatch, _timeline_state(2))
    result = tools["vf_export"](
        action="mp4",
        project_id=record.project_id,
        mode="preview",
        qa_mode="skip",
        wait=False,
    )
    assert result["ok"] is True
    assert result["action"] == "mp4"
    assert result["job"]["options"]["qa_mode"] == "skip"


def test_invalid_export_action_lists_valid_actions(
    tmp_path: Path, monkeypatch
) -> None:
    tools, record, _job = _tools(tmp_path, monkeypatch, _timeline_state(2))
    result = tools["vf_export"](action="nexus", project_id=record.project_id)
    assert result["ok"] is False
    assert result["error_code"] == "unknown_action"
    assert "mp4" in result["valid_actions"]
