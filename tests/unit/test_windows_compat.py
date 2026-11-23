from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from vf_shared.contracts.locking import FileLock


def test_file_lock_is_exclusive_and_releasable(tmp_path: Path) -> None:
    path = tmp_path / "state.lock"
    first = FileLock(path, blocking=False)
    second = FileLock(path, blocking=False)
    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()
    assert second.acquire() is True
    second.release()


def test_peak_rss_is_optional_without_resource(monkeypatch) -> None:
    from videoflow.application import process_control

    monkeypatch.setattr(process_control, "resource", None)
    assert process_control.peak_rss_mb() is None


def test_core_modules_import_without_posix_only_modules(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    code = """
import builtins

# Preload third-party modules that legitimately choose fcntl/mcp on POSIX.
import mcp.server.stdio  # noqa: F401

_real_import = builtins.__import__


def _import(name, *args, **kwargs):
    if name in {"fcntl", "resource"}:
        raise ImportError(f"{name} is not available")
    return _real_import(name, *args, **kwargs)


builtins.__import__ = _import
import videoflow.api.app
import videoflow.application.projects
import videoflow.mcp_server.agent_tools
print("ok")
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(root / "src"), str(root / "packages" / "vf-shared" / "src")]
    )
    env["VIDEOWFLOW_HOME"] = str(tmp_path)
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "ok" in completed.stdout
