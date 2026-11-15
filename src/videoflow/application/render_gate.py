"""Process-wide and cross-process gate for heavy renders.

FFmpeg and browser renders are CPU/GPU/memory heavy. The recipe runner may
execute independent jobs in parallel, but only one heavy render should own the
machine at a time. The gate keeps a thread semaphore for in-process workers and
an advisory file lock for multiple VideoFlow processes.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from videoflow.runtime import portable_home

try:  # POSIX only; Windows keeps the in-process semaphore.
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]


@dataclass
class RenderGate:
    path: Path | None = None
    _semaphore: threading.BoundedSemaphore = field(
        default_factory=lambda: threading.BoundedSemaphore(1)
    )
    _state_lock: threading.Lock = field(default_factory=threading.Lock)
    _current: str = ""
    _queued: int = 0


    @contextlib.contextmanager
    def hold(self, kind: str, job_id: str = "") -> Iterator[None]:
        """Wait for the single heavy-render slot and hold the process lock."""

        label = f"{kind}:{job_id}".strip(":")
        with self._state_lock:
            self._queued += 1
        entered = False
        try:
            with self._semaphore:
                with self._state_lock:
                    self._queued = max(0, self._queued - 1)
                    self._current = label
                entered = True
                handle = self._acquire_file_lock()
                try:
                    yield
                finally:
                    self._release_file_lock(handle)
        finally:
            with self._state_lock:
                if entered:
                    self._current = ""
                else:
                    self._queued = max(0, self._queued - 1)

    def _acquire_file_lock(self) -> object | None:
        if fcntl is None:
            return None
        path = self.path or (portable_home() / "render.lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except OSError:
            handle.close()
            return None
        return handle

    def _release_file_lock(self, handle: object | None) -> None:
        if handle is None or fcntl is None:
            return
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
        finally:
            handle.close()  # type: ignore[attr-defined]

    def status(self) -> dict[str, object]:
        with self._state_lock:
            return {
                "active": bool(self._current),
                "current": self._current,
                "queued": self._queued,
                "path": str(self.path or (portable_home() / "render.lock")),
                "cross_process": fcntl is not None,
            }


render_gate = RenderGate()


def reset_gate(path: Path | None = None) -> RenderGate:
    """Replace the global gate; used by tests and isolated workers."""

    global render_gate
    render_gate = RenderGate(path=path)
    return render_gate


__all__ = ["RenderGate", "render_gate", "reset_gate"]
