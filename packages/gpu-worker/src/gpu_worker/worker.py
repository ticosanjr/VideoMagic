"""Single-threaded background job runner."""

from __future__ import annotations

import queue
import shutil
import threading
from pathlib import Path

from gpu_worker.artifacts import ArtifactStore
from gpu_worker.handlers import HandlerError, HandlerRegistry
from gpu_worker.security import resolve_shared_path, safe_filename, unique_path
from gpu_worker.store import JobRecord, JobStore

_SENTINEL = "__stop__"


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
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifacts
        self._work_dir = Path(work_dir)
        self._shared_root = shared_root
        self._queue: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._stopped = threading.Event()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stopped.clear()
            self._thread = threading.Thread(target=self._loop, name="gpu-worker-job", daemon=True)
            self._thread.start()

    def submit(self, job_id: str) -> bool:
        if self._stopped.is_set():
            return False
        self._queue.put(job_id)
        return True

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None
        self._stopped.set()
        self._queue.put(_SENTINEL)
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)

    def _loop(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                if job_id == _SENTINEL:
                    return
                try:
                    self._run(job_id)
                except Exception:
                    # A metadata failure must not take the single worker thread down.
                    continue
            finally:
                self._queue.task_done()

    def _run(self, job_id: str) -> None:
        job = self._store.get_job(job_id)
        if job is None:
            return
        if not self._store.mark_running(job_id):
            return
        try:
            names = self._execute(job)
        except Exception as exc:
            self._store.finish_job(job_id, "failed", error=_error_text(exc))
            return
        self._store.finish_job(job_id, "succeeded", artifacts=names)

    def _execute(self, job: JobRecord) -> list[str]:
        job_dir = self._work_dir / "jobs" / job.id
        inputs_dir = job_dir / "inputs"
        artifacts_dir = job_dir / "artifacts"
        inputs_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

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
        results = handler(job.params, input_paths, job_dir) or []
        return self._collect_artifacts(job_dir, artifacts_dir, results)

    def _materialize_inputs(self, job: JobRecord, inputs_dir: Path) -> list[Path]:
        paths: list[Path] = []
        for index, artifact_id in enumerate(job.inputs):
            record = self._artifacts.get(artifact_id)
            if record is None:
                raise HandlerError(f"input artifact not found: {artifact_id}")
            suffix = record.path.suffix or ".bin"
            destination = inputs_dir / f"input_{index:03d}{suffix}"
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
