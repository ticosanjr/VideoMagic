"""Cross-platform process inspection and termination helpers."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    import resource
except ImportError:  # pragma: no cover - Windows
    resource = None  # type: ignore[assignment]


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
        if not handle:
            return kernel32.GetLastError() == 5
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _windows_parent_pid(pid: int) -> int:
    import ctypes
    from ctypes import wintypes

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot in {0, -1}:
        return 0
    entry = ProcessEntry32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        current = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while current:
            if int(entry.th32ProcessID) == int(pid):
                return int(entry.th32ParentProcessID)
            current = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return 0


def ancestor_pids(pid: int | None = None, *, limit: int = 64) -> set[int]:
    """Return the parent chain of ``pid`` without /proc on Windows."""

    current = int(pid or os.getpid())
    result: set[int] = set()
    while current > 1 and len(result) < max(1, limit):
        parent = 0
        if os.name == "nt":
            parent = _windows_parent_pid(current)
        else:
            try:
                stat = Path(f"/proc/{current}/stat").read_text(encoding="utf-8")
                parent = int(stat.rsplit(")", 1)[1].split()[1])
            except (OSError, ValueError, IndexError):
                parent = 0
        if parent <= 1 or parent in result:
            break
        result.add(parent)
        current = parent
    return result


def terminate_pid(pid: int, *, force: bool = False, timeout: float = 5.0) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    if os.name == "nt":
        command = ["taskkill", "/PID", str(pid), "/T"]
        if force:
            command.append("/F")
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0 and not force:
            return False
        deadline = time.monotonic() + max(0.1, timeout)
        while time.monotonic() < deadline and process_alive(pid):
            time.sleep(0.1)
        return not process_alive(pid)
    try:
        os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    deadline = time.monotonic() + max(0.1, timeout)
    while time.monotonic() < deadline and process_alive(pid):
        time.sleep(0.1)
    return not process_alive(pid)


def terminate_process(process: Any, *, timeout: float = 0.5) -> None:
    """Terminate an FFmpeg/service process and its children when possible."""

    poll = getattr(process, "poll", None)
    if callable(poll) and poll() is not None:
        return
    if os.name == "nt":
        process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2.0)
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()
        process.wait(timeout=2.0)


def peak_rss_mb() -> float | None:
    if resource is None:
        return None
    try:
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except (AttributeError, OSError, ValueError):
        return None


__all__ = [
    "ancestor_pids",
    "peak_rss_mb",
    "process_alive",
    "terminate_pid",
    "terminate_process",
]
