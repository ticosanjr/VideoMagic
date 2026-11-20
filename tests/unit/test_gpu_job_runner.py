from __future__ import annotations

import sys
import time
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[2] / "packages" / "gpu-worker" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from gpu_worker.artifacts import ArtifactStore  # noqa: E402
from gpu_worker.handlers import HandlerRegistry  # noqa: E402
from gpu_worker.store import JobStore  # noqa: E402
from gpu_worker.worker import JobRunner  # noqa: E402


def _runner(tmp_path: Path, cpu_workers: int = 2):
    store = JobStore(tmp_path / "store.sqlite")
    store.initialize()
    artifacts = ArtifactStore(tmp_path / "artifacts", store, max_bytes=10_000_000)
    registry = HandlerRegistry()

    def handler(params, inputs, work_dir):
        output = Path(work_dir) / f"{params['name']}.txt"
        output.write_text(str(params["name"]), encoding="utf-8")
        return [output]

    for capability in ("asr", "scene_analyze", "vision_blur"):
        registry.register_handler(capability, handler)
    runner = JobRunner(
        store=store,
        registry=registry,
        artifacts=artifacts,
        work_dir=tmp_path / "work",
        cpu_workers=cpu_workers,
    )
    return runner, store


def _submit(store: JobStore, job_id: str, capability: str, name: str) -> None:
    store.create_job(
        job_id=job_id,
        capability=capability,
        params={"name": name},
        inputs=[],
        shared_inputs=[],
    )


def _wait(store: JobStore, job_id: str, timeout: float = 5.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = store.get_job(job_id)
        if job is not None and job.status in {"succeeded", "failed"}:
            return job.status
        time.sleep(0.02)
    return "timeout"


def test_runner_records_metrics_for_cpu_jobs(tmp_path: Path) -> None:
    runner, store = _runner(tmp_path)
    runner.start()
    try:
        _submit(store, "cpu-1", "scene_analyze", "one")
        runner.submit("cpu-1")
        assert _wait(store, "cpu-1") == "succeeded"
        metrics = runner.metrics()
        assert metrics["completed"] == 1
        assert metrics["recent"][0]["capability"] == "scene_analyze"
        assert metrics["recent"][0]["status"] == "succeeded"
    finally:
        runner.stop()


def test_runner_uses_cpu_pool_not_the_gpu_lane(tmp_path: Path) -> None:
    runner, store = _runner(tmp_path, cpu_workers=2)
    runner.start()
    try:
        _submit(store, "cpu-a", "vision_blur", "a")
        _submit(store, "cpu-b", "vision_blur", "b")
        started = time.perf_counter()
        runner.submit("cpu-a")
        runner.submit("cpu-b")
        assert _wait(store, "cpu-a") == "succeeded"
        assert _wait(store, "cpu-b") == "succeeded"
        assert time.perf_counter() - started < 1.0
        assert runner.metrics()["cpu_workers"] == 2
    finally:
        runner.stop()


def test_runner_persists_handler_progress(tmp_path: Path) -> None:
    import threading

    from gpu_worker.progress import report

    runner, store = _runner(tmp_path)
    started = threading.Event()
    release = threading.Event()

    def slow_handler(params, inputs, work_dir):
        report("halfway", 42)
        started.set()
        release.wait(5.0)
        output = Path(work_dir) / "slow.txt"
        output.write_text("done", encoding="utf-8")
        return [output]

    runner._registry.register_handler("asr", slow_handler)
    runner.start()
    try:
        _submit(store, "slow-1", "asr", "slow")
        runner.submit("slow-1")
        assert started.wait(5.0)
        job = store.get_job("slow-1")
        assert job is not None
        assert job.stage == "halfway"
        assert job.progress == 42
        release.set()
        assert _wait(store, "slow-1") == "succeeded"
        finished = store.get_job("slow-1")
        assert finished is not None
        assert finished.progress == 100
        assert finished.stage == "succeeded"
    finally:
        release.set()
        runner.stop()


def test_runner_metrics_orders_queue_by_priority(tmp_path: Path) -> None:
    runner, store = _runner(tmp_path)
    store.create_job(
        job_id="low", capability="scene_analyze", params={}, inputs=[], shared_inputs=[],
        priority=0,
    )
    store.create_job(
        job_id="high", capability="scene_analyze", params={}, inputs=[], shared_inputs=[],
        priority=10,
    )
    metrics = runner.metrics()
    assert [item["job_id"] for item in metrics["queue"]] == ["high", "low"]
    assert metrics["queue"][0]["position"] == 1
