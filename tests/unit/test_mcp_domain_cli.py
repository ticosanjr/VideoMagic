"""Packaged domain MCP servers: imports, CLI dispatch, and PyInstaller wiring."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from videoflow import cli

ROOT = Path(__file__).resolve().parents[2]

MODULES = {
    "mcp-fetch": "mcp_fetch.server",
    "mcp-audio": "videoflow_mcp_audio.server",
    "mcp-vision": "videoflow_mcp_vision.server",
}


class FakeServer:
    def __init__(self) -> None:
        self.modes: list[str] = []

    def run(self, mode: str) -> None:
        self.modes.append(mode)


@pytest.mark.parametrize("command,module_name", sorted(MODULES.items()))
def test_domain_mcp_modules_import(command: str, module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert callable(module.build_server)


@pytest.mark.parametrize("command,module_name", sorted(MODULES.items()))
def test_domain_mcp_cli_dispatches_stdio(command: str, module_name: str, monkeypatch) -> None:
    module = importlib.import_module(module_name)
    server = FakeServer()
    monkeypatch.setattr(module, "build_server", lambda: server)

    assert cli.main([command]) == 0
    assert server.modes == ["stdio"]


def test_domain_servers_are_available_to_the_opencode_config() -> None:
    from videoflow.application.opencode_config import server_block

    assert server_block("fetch", workspace_root="/w")["command"][-1] == "videoflow-mcp-fetch"
    assert server_block("audio", workspace_root="/w")["command"][-1] == "videoflow-mcp-audio"
    assert server_block("vision", workspace_root="/w")["command"][-1] == "videoflow-mcp-vision"


def test_pyinstaller_spec_collects_domain_mcp_packages() -> None:
    spec = (ROOT / "packaging" / "videoflow.spec").read_text(encoding="utf-8")
    for package in ("mcp_fetch", "videoflow_mcp_audio", "videoflow_mcp_vision"):
        assert package in spec
    assert "videoflow-mcp-fetch" in spec
    assert "videoflow-mcp-audio" in spec
    assert "videoflow-mcp-vision" in spec
