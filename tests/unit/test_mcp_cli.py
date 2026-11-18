"""The stdio MCP entry point and prompt opt-out."""

from __future__ import annotations

import pytest

from videoflow.mcp_server import cli


class FakeServer:
    def __init__(self) -> None:
        self.modes: list[str] = []

    def run(self, mode: str) -> None:
        self.modes.append(mode)


def test_prompts_enabled_reads_flag_and_environment(monkeypatch) -> None:
    monkeypatch.delenv("VF_MCP_PROMPTS", raising=False)
    assert cli.prompts_enabled() is True
    assert cli.prompts_enabled(flag=True) is False
    for value in ("0", "false", "no", "off"):
        monkeypatch.setenv("VF_MCP_PROMPTS", value)
        assert cli.prompts_enabled() is False
    monkeypatch.setenv("VF_MCP_PROMPTS", "1")
    assert cli.prompts_enabled() is True


@pytest.mark.parametrize("argv,expected", [([], True), (["--no-prompts"], False)])
def test_main_forwards_prompt_flag(monkeypatch, argv, expected) -> None:
    captured: dict[str, object] = {}
    server = FakeServer()

    def fake_build(*args, prompts: bool = True) -> FakeServer:
        captured["prompts"] = prompts
        return server

    monkeypatch.setattr(cli, "build_server", fake_build)
    monkeypatch.delenv("VF_MCP_PROMPTS", raising=False)
    cli.main(argv)
    assert captured["prompts"] is expected
    assert server.modes == ["stdio"]
