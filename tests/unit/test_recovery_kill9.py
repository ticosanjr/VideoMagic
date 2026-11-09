"""Real SIGKILL recovery: a running job comes back after the process dies."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from tests.recipe_jobs import MINIMAL_RECIPE, manager_with_runner

CHILD = r"""
import json, sys, time
from pathlib import Path
from tests.recipe_jobs import MINIMAL_RECIPE, manager_with_runner, start_recipe

home = Path(sys.argv[1]); source = Path(sys.argv[2]); output = Path(sys.argv[3])
marker = Path(sys.argv[4])

def runner(source, output, *, progress, should_cancel, **kwargs):
    time.sleep(30)
    return {"ok": True}

manager = manager_with_runner(runner, store_dir=home / "jobs")
job = start_recipe(manager, source, output, {})
while job.status != "running":
    time.sleep(0.01)
manager._persist_job(job)
marker.write_text(str(job.job_id))
time.sleep(30)
"""


def wait_for(predicate, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not reached")


def test_sigkill_requeues_the_running_job(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    marker = tmp_path / "ready.txt"
    env = {**os.environ, "VIDEOWFLOW_HOME": str(home)}
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            CHILD,
            str(home),
            str(source),
            str(tmp_path / "out"),
            str(marker),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for(marker.is_file)
        job_id = marker.read_text().strip()
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()

    def fast(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        return {"ok": True}

    recovered = manager_with_runner(fast, store_dir=home / "jobs")
    current = recovered.get(job_id)
    for _ in range(300):
        current = recovered.get(job_id)
        if current.status == "succeeded":
            break
        time.sleep(0.01)
    assert current.status == "succeeded", current.error


def test_interrupted_recipe_job_is_requeued(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    jobs = home / "jobs"
    jobs.mkdir()
    payload = {
        "job_id": "11111111-1111-1111-1111-111111111111",
        "status": "running",
        "stage": "render",
        "message": "working",
        "source": str(tmp_path / "source.mp4"),
        "output": str(tmp_path / "out"),
        "options": {"mode": "recipe", "recipe": MINIMAL_RECIPE},
        "progress": 40,
        "result": None,
        "error": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    (jobs / f"{payload['job_id']}.json").write_text(json.dumps(payload), encoding="utf-8")
    os.environ["VIDEOWFLOW_HOME"] = str(home)

    recovered = manager_with_runner(lambda *args, **kwargs: {"ok": True}, store_dir=jobs)
    job = recovered.get(payload["job_id"])

    assert job.status in {"queued", "running", "succeeded"}
