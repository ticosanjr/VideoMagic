"""Single-threaded background job runner."""

from __future__ import annotations

import contextlib
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
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifacts
        self._work_dir = Path(work_dir)
        self._shared_root = shared_root
        self._models = models
        self._vram = vram
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
            names, shared, shared_error = self._execute(job)
        except Exception as exc:
            self._store.finish_job(job_id, "failed", error=_error_text(exc))
            return
        self._store.finish_job(
            job_id,
            "succeeded",
            artifacts=names,
            shared_artifacts=shared,
            shared_error=shared_error,
        )

    def _execute(self, job: JobRecord) -> tuple[list[str], list[str], str | None]:
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
        if self._vram is not None and self._models is not None:
            try:
                self._vram.ensure(vram_cost(job.capability), self._models)
            except VramError as exc:
                raise HandlerError(str(exc)) from exc
        materialized = _materialize_params(job.params, input_paths)
        params = materialized if isinstance(materialized, dict) else job.params
        results = handler(params, input_paths, job_dir) or []
        names = self._collect_artifacts(job_dir, artifacts_dir, results)
        shared, shared_error = self._write_shared_outputs(job, artifacts_dir, names)
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
