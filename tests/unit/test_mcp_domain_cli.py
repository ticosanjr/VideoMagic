"""One unified MCP server: CLI dispatch, config, and packaging wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from videoflow import cli

ROOT = Path(__file__).resolve().parents[2]


class FakeServer:
    def __init__(self) -> None:
        self.modes: list[str] = []

    def run(self, mode: str) -> None:
        self.modes.append(mode)


def test_unified_mcp_cli_dispatches_stdio(monkeypatch) -> None:
    from videoflow.mcp_server import server as server_module

    server = FakeServer()
    monkeypatch.setattr(server_module, "build_server", lambda **kwargs: server)

    assert cli.main(["mcp"]) == 0
    assert server.modes == ["stdio"]


@pytest.mark.parametrize("command", ["mcp-fetch", "mcp-audio", "mcp-vision"])
def test_legacy_domain_mcp_subcommands_are_gone(command: str) -> None:
    with pytest.raises(SystemExit):
        cli.main([command])


def test_only_the_core_server_block_is_supported() -> None:
    from videoflow.application.opencode_config import server_block

    core = server_block("core", workspace_root="/w")
    assert core["command"]
    for name in ("fetch", "audio", "vision"):
        with pytest.raises(ValueError):
            server_block(name, workspace_root="/w")


def test_pyinstaller_spec_no_longer_collects_domain_packages() -> None:
    spec = (ROOT / "packaging" / "videoflow.spec").read_text(encoding="utf-8")
    for package in ("mcp_fetch", "videoflow_mcp_audio", "videoflow_mcp_vision"):
        assert package not in spec
    assert "videoflow-mcp-fetch" not in spec
    assert "videoflow-mcp-audio" not in spec
    assert "videoflow-mcp-vision" not in spec
