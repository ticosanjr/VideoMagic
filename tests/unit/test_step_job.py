"""Real step jobs operate on the project timeline."""

from __future__ import annotations

import time
from pathlib import Path

from videoflow.application.jobs import JobManager
from videoflow.application.projects import init_project, load_project_state, save_project_state
from videoflow.domain.state import MediaInfo, OverlayClip, ProjectState


def test_step_job_runs_against_project_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    record, _ = init_project(output=tmp_path / "out")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )
    state = ProjectState(
        media_info=media,
        overlays=[
            OverlayClip(
                overlay_id="o1",
                path=str(tmp_path / "logo.png"),
                start_frame=0,
                duration_frames=30,
                anchor="top_right",
                margin_x=0,
                margin_y=0,
                width_ratio=0.2,
            )
        ],
    )
    save_project_state(record, state, bump_revision=False)
    manager = JobManager(max_active=1, history=10)
    job = manager.start(
        source,
        Path(record.output),
        {
            "mode": "step",
            "project_id": record.project_id,
            "step_type": "qa.safezone",
            "params": {"platforms": ["reels"], "include_overlays": True},
        },
        queue=False,
        project_id=record.project_id,
    )
    deadline = time.monotonic() + 30
    while job.status not in {"succeeded", "failed", "cancelled"} and time.monotonic() < deadline:
        time.sleep(0.05)
        job = manager.get(str(job.job_id))
    assert job.status == "succeeded", job.error
    assert job.result is not None
    assert job.result["step_id"] == "qa.safezone"
    assert Path(job.result["artifacts"]["safezone_report"]).is_file()
    assert load_project_state(record).revision >= state.revision
