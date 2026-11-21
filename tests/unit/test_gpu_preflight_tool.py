from __future__ import annotations

from pathlib import Path

import pytest
from vf_shared.compute.models import WorkerHealth

from videoflow.application.jobs import JobManager
from videoflow.mcp_server.context import ToolContext
from videoflow.mcp_server.core_tools import register_core_tools


class _OfflineRouter:
    mode = "auto"
    transport = "http"
    worker_url = "http://worker:8766"

    def health(self, force: bool = False) -> WorkerHealth:
        return WorkerHealth(available=False, message="offline")


def _tools(tmp_path: Path, router: object) -> dict[str, object]:
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager),
    )
    return tools


def test_gpu_preflight_degrades_when_worker_is_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "videoflow.application.compute.router_from_settings",
        lambda settings=None: _OfflineRouter(),
    )
    tools = _tools(tmp_path, _OfflineRouter())
    result = tools["vf_gpu_preflight"]()
    assert result["ok"] is True
    assert result["remote_available"] is False
    assert result["degraded"] is True
    assert result["degraded_reason"] == "windows_gpu_offline_fallback_cpu"
    assert result["transport"] == "http"


def test_gpu_preflight_requires_gpu_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "videoflow.application.compute.router_from_settings",
        lambda settings=None: _OfflineRouter(),
    )
    tools = _tools(tmp_path, _OfflineRouter())
    result = tools["vf_gpu_preflight"](require_gpu=True)
    assert result["ok"] is False
    assert result["error_code"] == "gpu_worker_unreachable"
