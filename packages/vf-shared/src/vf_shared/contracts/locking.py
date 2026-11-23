"""Cross-platform advisory file locks for shared state files."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import BinaryIO

_LOCAL_LOCKS: dict[str, threading.Lock] = {}
_LOCAL_GUARD = threading.Lock()


def _local_lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _LOCAL_GUARD:
        return _LOCAL_LOCKS.setdefault(key, threading.Lock())


class FileLock:
    """A small process/thread lock backed by ``fcntl`` or ``msvcrt``.

    The fallback is process-local only. It keeps the application usable on
    platforms without an advisory lock API instead of failing at import time.
    """

    def __init__(self, path: Path, *, blocking: bool = True) -> None:
        self.path = Path(path)
        self.blocking = blocking
        self.handle: BinaryIO | None = None
        self._local: threading.Lock | None = None
        self._local_acquired = False

    def acquire(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        if os.name == "nt":
            try:
                import msvcrt
            except ImportError:
                return self._acquire_local()
        else:
            try:
                import fcntl
            except ImportError:
                return self._acquire_local()
        try:
            handle = self.path.open("a+b")
        except OSError:
            return False
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                if handle.read(1) == b"":
                    handle.seek(0)
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                mode = msvcrt.LK_LOCK if self.blocking else msvcrt.LK_NBLCK
                msvcrt.locking(handle.fileno(), mode, 1)
            else:
                import fcntl

                flags = fcntl.LOCK_EX
                if not self.blocking:
                    flags |= fcntl.LOCK_NB
                fcntl.flock(handle.fileno(), flags)
        except OSError:
            handle.close()
            return False
        self.handle = handle
        return True

    def _acquire_local(self) -> bool:
        lock = _local_lock(self.path)
        if self.blocking:
            lock.acquire()
            self._local_acquired = True
        elif not lock.acquire(blocking=False):
            return False
        else:
            self._local_acquired = True
        self._local = lock
        return True

    def release(self) -> None:
        handle = self.handle
        if handle is not None:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass
            finally:
                handle.close()
                self.handle = None
        if self._local is not None and self._local_acquired:
            self._local.release()
            self._local = None
            self._local_acquired = False

    def __enter__(self) -> FileLock:
        if not self.acquire():
            raise OSError(f"could not acquire file lock: {self.path}")
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()


__all__ = ["FileLock"]
