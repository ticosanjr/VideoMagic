import asyncio
import json

import pytest

from videoflow.mcp_server.registry import (
    RESOURCE_SPECS,
    TOOL_SPECS,
    not_implemented_payload,
)
from videoflow.mcp_server.server import build_server


def test_registry_names_are_unique_and_prefixed() -> None:
    names = [tool.name for tool in TOOL_SPECS]
    assert len(names) == len(set(names))
    assert all(name.startswith("videoflow_") for name in names)
    assert len(RESOURCE_SPECS) == 4


def test_not_implemented_payload_shape() -> None:
    payload = not_implemented_payload("videoflow_transcribe")
    assert payload["ok"] is False
    assert payload["code"] == "not_implemented"
    assert payload["tool"] == "videoflow_transcribe"


def test_server_registers_every_public_tool() -> None:
    async def inspect() -> list[str]:
        return [tool.name for tool in await build_server().list_tools()]

    assert sorted(asyncio.run(inspect())) == sorted(tool.name for tool in TOOL_SPECS)


def test_tool_call_returns_a_structured_not_implemented_result() -> None:
    async def call() -> object:
        return await build_server().call_tool(
            "videoflow_transcribe", {"model": "small", "language": "pt"}
        )

    result = asyncio.run(call())
    structured = result.structured_content  # type: ignore[attr-defined]
    assert structured["code"] == "not_implemented"
    assert structured["tool"] == "videoflow_transcribe"
    text = json.loads(result.content[0].text)  # type: ignore[attr-defined]
    assert text["ok"] is False


@pytest.mark.xfail(reason="Transcript resource lands with the job pass", strict=True)
def test_transcript_resource_returns_real_text() -> None:
    raise AssertionError("no live project in the scaffold")
