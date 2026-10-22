"""Sequential folder batches backed by the existing JobManager.

One batch runs one file at a time. This keeps CPU and disk pressure predictable
and lets every item reuse the normal recipe checkpoints.
"""

from __future__ import annotations

import contextlib
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from videoflow.application.jobs import TERMINAL, JobManager
from videoflow.domain.errors import BatchError, JobQueueFullError, VideoFlowError

MEDIA_EXTENSIONS = frozenset(
    {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".mts", ".m2ts", ".mpg", ".mpeg"}
)
BatchStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
ItemStatus = Literal["pending", "running", "succeeded", "failed", "cancelled"]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@dataclass
class BatchItem:
    source: Path
    output: Path
    status: ItemStatus = "pending"
    job_id: str | None = None
    message: str = "Waiting"
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": str(self.source),
            "output": str(self.output),
            "status": self.status,
            "job_id": self.job_id,
            "message": self.message,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass
class Batch:
    source_dir: Path
    output_root: Path
    recipe_id: str
    recipe: dict[str, Any]
    items: list[BatchItem]
    resume: bool = True
    batch_id: UUID = field(default_factory=uuid4)
    status: BatchStatus = "queued"
    completed: int = 0
    failed: int = 0
    current_job_id: str | None = None
    cancel_requested: bool = False
    message: str = "Waiting"
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None

    @property
    def total(self) -> int:
        return len(self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": str(self.batch_id),
            "status": self.status,
            "message": self.message,
            "source_dir": str(self.source_dir),
            "output_root": str(self.output_root),
            "recipe_id": self.recipe_id,
            "resume": self.resume,
            "total": len(self.items),
            "completed": self.completed,
            "failed": self.failed,
            "current_job_id": self.current_job_id,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "items": [item.to_dict() for item in self.items],
        }


class BatchManager:
    """In-process batch queue. Batch history is intentionally not persisted."""

    def __init__(self, jobs: JobManager, *, history: int = 20) -> None:
        self._jobs = jobs
        self._history = history
        self._batches: dict[str, Batch] = {}
        self._lock = threading.Lock()

    def start(
        self,
        source_dir: Path,
        output_root: Path,
        recipe: dict[str, Any],
        *,
        recipe_id: str = "recipe",
        recursive: bool = False,
        extensions: list[str] | None = None,
        resume: bool = True,
        max_files: int = 200,
    ) -> Batch:
        directory = Path(source_dir).expanduser().resolve()
        if not directory.is_dir():
            raise BatchError(f"Batch source is not a directory: {directory}")
        root = Path(output_root).expanduser().resolve()
        allowed = {
            (item if item.startswith(".") else f".{item}").casefold()
            for item in (extensions or MEDIA_EXTENSIONS)
        }
        pattern = "**/*" if recursive else "*"
        files = [
            path
            for path in sorted(directory.glob(pattern))
            if path.is_file()
            and not any(part.startswith(".") for part in path.relative_to(directory).parts)
            and path.suffix.casefold() in allowed
        ][: max(1, min(int(max_files), 2000))]
        if not files:
            raise BatchError(f"No media files matched {directory} ({', '.join(sorted(allowed))})")
        root.mkdir(parents=True, exist_ok=True)
        items = []
        for path in files:
            relative = path.relative_to(directory).with_suffix("")
            items.append(
                BatchItem(
                    source=path,
                    output=root / relative.parent / f"{relative.name}-videoflow",
                )
            )
        batch = Batch(
            source_dir=directory,
            output_root=root,
            recipe_id=recipe_id,
            recipe=recipe,
            items=items,
            resume=resume,
        )
        with self._lock:
            self._prune()
            self._batches[str(batch.batch_id)] = batch
        thread = threading.Thread(
            target=self._work,
            args=(batch,),
            name=f"videoflow-batch-{batch.batch_id}",
            daemon=True,
        )
        thread.start()
        return batch

    def get(self, batch_id: str) -> Batch:
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                raise BatchError(f"Unknown batch: {batch_id}")
            return batch

    def list(self) -> list[Batch]:
        with self._lock:
            return sorted(self._batches.values(), key=lambda item: item.created_at, reverse=True)

    def cancel(self, batch_id: str) -> Batch:
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                raise BatchError(f"Unknown batch: {batch_id}")
            if batch.status in {"succeeded", "failed", "cancelled"}:
                return batch
            batch.cancel_requested = True
            batch.message = "Cancellation requested"
            if batch.current_job_id:
                with contextlib.suppress(VideoFlowError):
                    self._jobs.cancel(batch.current_job_id)
            return batch

    def _work(self, batch: Batch) -> None:
        with self._lock:
            batch.status = "running"
            batch.started_at = _now()
            batch.message = "Starting batch"
        try:
            for item in batch.items:
                if batch.cancel_requested:
                    item.status = "cancelled"
                    item.message = "Cancelled before start"
                    continue
                with self._lock:
                    item.status = "running"
                    item.started_at = _now()
                    item.message = "Starting"
                job = None
                while job is None:
                    if batch.cancel_requested:
                        item.status = "cancelled"
                        item.message = "Cancelled before start"
                        break
                    try:
                        job = self._jobs.start(
                            item.source,
                            item.output,
                            {
                                "mode": "recipe",
                                "recipe": batch.recipe,
                                "resume": batch.resume,
                            },
                        )
                    except JobQueueFullError:
                        time.sleep(0.5)
                if job is None:
                    with self._lock:
                        batch.completed += 1
                    continue
                with self._lock:
                    batch.current_job_id = str(job.job_id)
                    item.job_id = str(job.job_id)
                while True:
                    current = self._jobs.get(str(job.job_id))
                    if current.status in TERMINAL:
                        break
                    if batch.cancel_requested:
                        self._jobs.cancel(str(job.job_id))
                    time.sleep(0.5)
                current = self._jobs.get(str(job.job_id))
                with self._lock:
                    item.status = current.status  # type: ignore[assignment]
                    item.message = current.message
                    item.finished_at = _now()
                    batch.completed += 1
                    if current.status == "failed":
                        batch.failed += 1
                    batch.current_job_id = None
                    batch.message = f"{batch.completed}/{len(batch.items)} processed"
                if batch.cancel_requested:
                    break
        finally:
            with self._lock:
                if batch.cancel_requested:
                    batch.status = "cancelled"
                    batch.message = "Cancelled"
                elif batch.failed:
                    batch.status = "failed"
                    batch.message = f"{batch.failed} of {len(batch.items)} failed"
                else:
                    batch.status = "succeeded"
                    batch.message = "Finished"
                batch.finished_at = _now()

    def _prune(self) -> None:
        finished = [
            batch
            for batch in self._batches.values()
            if batch.status in {"succeeded", "failed", "cancelled"}
        ]
        if len(finished) <= self._history:
            return
        finished.sort(key=lambda item: item.finished_at or "")
        for batch in finished[: len(finished) - self._history]:
            self._batches.pop(str(batch.batch_id), None)
