"""Single-threaded background job runner."""

from __future__ import annotations

import contextlib
import itertools
import os
import queue
import re
import shutil
import threading
import time
from pathlib import Path

from gpu_worker.artifacts import ArtifactStore
from gpu_worker.capabilities import vram_cost
from gpu_worker.handlers import HandlerError, HandlerRegistry
from gpu_worker.models import ModelRegistry
from gpu_worker.progress import bind as bind_progress
from gpu_worker.security import (
    UnsafePathError,
    resolve_shared_output,
    resolve_shared_path,
    safe_filename,
    unique_path,
)
from gpu_worker.store import JobRecord, JobStore
from gpu_worker.vram import VramBudget, VramError

_SENTINEL = "__stop__"
_SENTINEL_PRIORITY = 10_000
_CPU_CAPABILITIES = frozenset({"scene_analyze", "vision_blur", "audio_events"})
_INPUT_PLACEHOLDER = re.compile(r"^__VF_INPUT_(\d+)__$")


def _materialize_params(value: object, input_paths: list[Path]) -> object:
    """Replace ``__VF_INPUT_n__`` placeholders with materialized local paths."""

    if isinstance(value, str):
        match = _INPUT_PLACEHOLDER.fullmatch(value)
        if match is None:
            return value
        index = int(match.group(1))
        if 0 <= index < len(input_paths):
            return str(input_paths[index])
        return value
    if isinstance(value, dict):
        return {str(key): _materialize_params(item, input_paths) for key, item in value.items()}
    if isinstance(value, list):
        return [_materialize_params(item, input_paths) for item in value]
    return value


class JobRunner:
    """Run one GPU job at a time from a FIFO queue."""

    def __init__(
        self,
        *,
        store: JobStore,
        registry: HandlerRegistry,
        artifacts: ArtifactStore,
        work_dir: Path,
        shared_root: Path | None = None,
        models: ModelRegistry | None = None,
        vram: VramBudget | None = None,
        cpu_workers: int = 2,
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifacts
        self._work_dir = Path(work_dir)
        self._shared_root = shared_root
        self._models = models
        self._vram = vram
        self._gpu_queue: queue.PriorityQueue[tuple[int, int, str]] = queue.PriorityQueue()
        self._cpu_queue: queue.PriorityQueue[tuple[int, int, str]] = queue.PriorityQueue()
        self._sequence = itertools.count()
        self._cpu_workers = max(1, min(int(cpu_workers), 8))
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._metrics: list[dict[str, object]] = []
        self._current: dict[str, dict[str, object]] = {}
        self._metrics_lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._threads and any(thread.is_alive() for thread in self._threads):
                return
            self._stopped.clear()
            self._threads = [
                threading.Thread(
                    target=self._loop,
                    args=(self._gpu_queue,),
                    name="gpu-worker-gpu",
                    daemon=True,
                )
            ]
            self._threads.extend(
                threading.Thread(
                    target=self._loop,
                    args=(self._cpu_queue,),
                    name=f"gpu-worker-cpu-{index + 1}",
                    daemon=True,
                )
                for index in range(self._cpu_workers)
            )
            for thread in self._threads:
                thread.start()

    def submit(self, job_id: str, priority: int = 0) -> bool:
        if self._stopped.is_set():
            return False
        job = self._store.get_job(job_id)
        is_cpu = job is not None and job.capability in _CPU_CAPABILITIES
        effective = int(job.priority) if job is not None and priority == 0 else int(priority)
        item = (-effective, next(self._sequence), job_id)
        (self._cpu_queue if is_cpu else self._gpu_queue).put(item)
        return True

    def stop(self) -> None:
        with self._lock:
            threads = list(self._threads)
            self._threads = []
        self._stopped.set()
        self._gpu_queue.put((-_SENTINEL_PRIORITY, 0, _SENTINEL))
        for _ in range(self._cpu_workers):
            self._cpu_queue.put((-_SENTINEL_PRIORITY, 0, _SENTINEL))
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=5.0)

    def metrics(self) -> dict[str, object]:
        with self._metrics_lock:
            recent = list(self._metrics)
            current = [
                {
                    **item,
                    "running_sec": round(
                        max(0.0, time.time() - float(item["started_at"])), 3
                    ),
                }
                for item in self._current.values()
            ]
        averages: dict[str, float] = {}
        for item in recent:
            capability = str(item.get("capability") or "")
            elapsed = float(item.get("elapsed_sec") or 0.0)
            if not capability or elapsed <= 0:
                continue
            previous = averages.get(capability, elapsed)
            averages[capability] = (previous + elapsed) / 2.0
        queued = self._store.queued_jobs()
        queue: list[dict[str, object]] = []
        wait = 0.0
        for position, job in enumerate(queued, start=1):
            estimate = averages.get(job.capability, 0.0)
            wait += estimate
            queue.append(
                {
                    "job_id": job.id,
                    "capability": job.capability,
                    "priority": job.priority,
                    "position": position,
                    "estimated_wait_sec": round(wait, 3),
                }
            )
        return {
            "cpu_workers": self._cpu_workers,
            "recent": recent[-20:],
            "current": current,
            "queue": queue,
            "queued": len(queue),
            "completed": len(recent),
            "average_elapsed_sec": {
                key: round(value, 3) for key, value in sorted(averages.items())
            },
        }

    def _progress(self, job_id: str, stage: str, progress: int) -> None:
        self._store.update_progress(job_id, stage, progress)
        with self._metrics_lock:
            current = self._current.get(job_id)
            if current is not None:
                current["stage"] = stage
                current["progress"] = progress

    def _loop(self, queue_: queue.PriorityQueue[tuple[int, int, str]]) -> None:
        while True:
            _priority, _sequence, job_id = queue_.get()
            try:
                if job_id == _SENTINEL:
                    return
                try:
                    self._run(job_id)
                except Exception:
                    # A metadata failure must not take the worker thread down.
                    continue
            finally:
                queue_.task_done()

    def _run(self, job_id: str) -> None:
        job = self._store.get_job(job_id)
        if job is None:
            return
        if not self._store.mark_running(job_id):
            return
        job = self._store.get_job(job_id) or job
        started = time.perf_counter()
        with self._metrics_lock:
            self._current[job_id] = {
                "job_id": job_id,
                "capability": job.capability,
                "stage": "starting",
                "progress": 1,
                "started_at": time.time(),
                "running_sec": 0.0,
            }
        try:
            with bind_progress(lambda stage, value: self._progress(job_id, stage, value)):
                names, shared, shared_error = self._execute(job)
        except Exception as exc:
            self._store.finish_job(job_id, "failed", error=_error_text(exc))
            self._record_metric(job, started, "failed", _error_text(exc))
            return
        self._store.finish_job(
            job_id,
            "succeeded",
            artifacts=names,
            shared_artifacts=shared,
            shared_error=shared_error,
        )
        self._record_metric(job, started, "succeeded", "")

    def _record_metric(self, job: JobRecord, started: float, status: str, error: str) -> None:
        elapsed = round(time.perf_counter() - started, 3)
        queue_wait = max(0.0, round((job.started_at or job.created_at) - job.created_at, 3))
        record = {
            "job_id": job.id,
            "capability": job.capability,
            "priority": job.priority,
            "status": status,
            "queue_wait_sec": queue_wait,
            "elapsed_sec": elapsed,
            "error": error,
            "finished_at": time.time(),
        }
        with self._metrics_lock:
            self._current.pop(job.id, None)
            self._metrics.append(record)
            self._metrics = self._metrics[-100:]

    def _execute(self, job: JobRecord) -> tuple[list[str], list[str], str | None]:
        from gpu_worker.progress import report

        job_dir = self._work_dir / "jobs" / job.id
        inputs_dir = job_dir / "inputs"
        artifacts_dir = job_dir / "artifacts"
        inputs_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        report("preparing inputs", 3)
        input_paths = self._materialize_inputs(job, inputs_dir)
        for relative in job.shared_inputs:
            if self._shared_root is None:
                raise HandlerError("shared inputs are not configured")
            input_paths.append(resolve_shared_path(self._shared_root, relative))

        handler = self._registry.get(job.capability)
        if handler is None:
            raise HandlerError(
                f"capability '{job.capability}' is unavailable: "
                f"{self._registry.reason(job.capability)}"
            )
        if (
            job.capability not in _CPU_CAPABILITIES
            and self._vram is not None
            and self._models is not None
        ):
            report("reserving vram", 6)
            try:
                self._vram.ensure(vram_cost(job.capability), self._models)
            except VramError as exc:
                raise HandlerError(str(exc)) from exc
        materialized = _materialize_params(job.params, input_paths)
        params = materialized if isinstance(materialized, dict) else job.params
        report("running", 10)
        results = handler(params, input_paths, job_dir) or []
        report("collecting artifacts", 92)
        names = self._collect_artifacts(job_dir, artifacts_dir, results)
        if job.shared_outputs:
            report("writing shared outputs", 96)
        shared, shared_error = self._write_shared_outputs(job, artifacts_dir, names)
        report("finishing", 99)
        return names, shared, shared_error

    def _write_shared_outputs(
        self,
        job: JobRecord,
        artifacts_dir: Path,
        names: list[str],
    ) -> tuple[list[str], str | None]:
        if not job.shared_outputs:
            return [], None
        if self._shared_root is None:
            raise HandlerError("shared outputs are not configured")
        if len(job.shared_outputs) > len(names):
            raise HandlerError(
                "more shared_outputs were requested than artifacts produced "
                f"({len(job.shared_outputs)} > {len(names)})"
            )
        written: list[str] = []
        errors: list[str] = []
        for relative, name in zip(job.shared_outputs, names, strict=False):
            try:
                target = resolve_shared_output(self._shared_root, relative)
            except (OSError, UnsafePathError) as exc:
                errors.append(f"{relative}: {exc}")
                continue
            temporary = target.with_name(f".{target.name}.part")
            last_error: OSError | None = None
            for _attempt in range(5):
                try:
                    shutil.copyfile(artifacts_dir / name, temporary)
                    with temporary.open("rb+") as handle:
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temporary, target)
                    if target.stat().st_size <= 0:
                        raise OSError("shared output is empty after write")
                    written.append(relative)
                    last_error = None
                    break
                except OSError as exc:
                    last_error = exc
                    time.sleep(0.2)
            if last_error is not None:
                with contextlib.suppress(OSError):
                    temporary.unlink(missing_ok=True)
                errors.append(f"{relative}: {last_error}")
        return written, ("; ".join(errors) if errors else None)

    def _materialize_inputs(self, job: JobRecord, inputs_dir: Path) -> list[Path]:
        paths: list[Path] = []
        for index, artifact_id in enumerate(job.inputs):
            record = self._artifacts.get(artifact_id)
            if record is None:
                raise HandlerError(f"input artifact not found: {artifact_id}")
            suffix = record.path.suffix or ".bin"
            destination = inputs_dir / f"input_{index:03d}{suffix}"
            try:
                os.link(record.path, destination)
            except OSError:
                shutil.copyfile(record.path, destination)
            paths.append(destination)
        return paths

    def _collect_artifacts(self, job_dir: Path, artifacts_dir: Path, results: object) -> list[str]:
        if not isinstance(results, list | tuple):
            raise HandlerError("handler must return a list of artifact paths")
        names: list[str] = []
        artifacts_resolved = artifacts_dir.resolve()
        for item in results:
            source = Path(item)
            if not source.is_absolute():
                source = job_dir / source
            try:
                resolved = source.resolve()
            except OSError as exc:
                raise HandlerError(f"handler returned an invalid artifact path: {item}") from exc
            if not resolved.is_file():
                raise HandlerError(f"handler returned a missing artifact: {item}")
            if resolved.parent == artifacts_resolved:
                names.append(resolved.name)
                continue
            name = safe_filename(resolved.name, default="artifact")
            destination = unique_path(artifacts_dir, name)
            shutil.copyfile(resolved, destination)
            names.append(destination.name)
        return names


def _error_text(exc: Exception) -> str:
    message = str(exc).strip()
    text = f"{type(exc).__name__}: {message}" if message else type(exc).__name__
    return text[:2000]
