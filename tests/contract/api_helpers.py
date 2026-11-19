from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from videoflow.api.app import create_app
from videoflow.application.jobs import JobManager
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment


def _runner(source: Path, output: Path, **kwargs):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    state = ProjectState(
        media_info=MediaInfo(
            source_path=str(source),
            duration_frames=100,
            fps_num=25,
            fps_den=1,
            width=320,
            height=240,
            audio_sample_rate=48000,
        ),
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_in_frame=0,
                source_out_frame=25,
                timeline_in_frame=0,
                timeline_out_frame=25,
            ),
            VideoSegment(
                clip_id="v2",
                source_in_frame=25,
                source_out_frame=50,
                timeline_in_frame=25,
                timeline_out_frame=50,
            ),
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            ),
            AudioSegment(
                clip_id="v2",
                source_in_sample=48000,
                source_out_sample=96000,
                timeline_in_sample=48000,
                timeline_out_sample=96000,
            ),
        ],
    )
    path = output / "project_state.json"
    path.write_text(state.model_dump_json(), encoding="utf-8")
    return {
        "ok": True,
        "state_path": str(path),
        "artifacts": {},
        "shorts": [],
        "broll_plan": {"Short one": [{"path": "/a.mp4"}, {"path": "/b.mp4"}]},
    }


MINIMAL_RECIPE = {
    "schema_version": 1,
    "id": "test",
    "name": "Test",
    "steps": [{"id": "ingest", "type": "ingest", "needs": []}],
}


class _FakeResult:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def to_dict(self) -> dict:
        return self._payload


class _FakeRecipeRunner:
    def run(self, source: Path, output: Path, **kwargs) -> _FakeResult:
        return _FakeResult(_runner(source, output, **kwargs))


def _client(
    monkeypatch, tmp_path: Path, *, real_recipe_runner: bool = False
) -> tuple[TestClient, JobManager]:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    manager = JobManager(
        recipe_runner_factory=(
            None if real_recipe_runner else lambda _recipe, _job: _FakeRecipeRunner()
        )
    )
    return TestClient(create_app(jobs=manager)), manager


def _job(manager: JobManager, tmp_path: Path):
    job = manager.start(
        tmp_path / "source.mp4",
        tmp_path / "out",
        {"mode": "recipe", "recipe": MINIMAL_RECIPE},
    )
    for _ in range(300):
        if job.status in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.01)
    assert job.status == "succeeded"
    return job
