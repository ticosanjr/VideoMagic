import asyncio
import json

from videoflow.mcp_server.registry import RESOURCE_SPECS, TOOL_SPECS
from videoflow.mcp_server.server import build_server


def test_registry_names_are_unique_and_prefixed() -> None:
    names = [tool.name for tool in TOOL_SPECS]
    assert len(names) == len(set(names))
    assert all(name.startswith("videoflow_") for name in names)
    assert len(RESOURCE_SPECS) == 4


def test_server_registers_every_public_tool() -> None:
    async def inspect() -> list[str]:
        return [tool.name for tool in await build_server().list_tools()]

    assert sorted(asyncio.run(inspect())) == sorted(tool.name for tool in TOOL_SPECS)


def test_tools_without_media_return_a_typed_error() -> None:
    async def call() -> object:
        return await build_server().call_tool(
            "videoflow_transcribe", {"model": "small", "language": "pt"}
        )

    result = asyncio.run(call())
    structured = result.structured_content  # type: ignore[attr-defined]
    assert structured["ok"] is False
    assert structured["code"] == "source_required"


def test_presets_resource_returns_builtin_and_shipped_presets() -> None:
    async def read() -> str:
        contents = await build_server().read_resource("videoflow://presets/list")
        return next(iter(contents)).content  # type: ignore[attr-defined]

    payload = json.loads(asyncio.run(read()))
    assert payload["ok"] is True
    assert "youtube-talking-head" in payload["presets"]
    assert "lecture-clean" in payload["presets"]


def test_state_and_transcript_resources_report_missing_state() -> None:
    async def read(uri: str) -> str:
        contents = await build_server().read_resource(uri)
        return next(iter(contents)).content  # type: ignore[attr-defined]

    state = json.loads(asyncio.run(read("videoflow://project/state")))
    transcript = json.loads(asyncio.run(read("videoflow://project/transcript")))
    assert state["code"] == "state_not_found"
    assert transcript["code"] == "transcript_not_found"


def test_capabilities_tool_reports_policy_and_short_aspects() -> None:
    async def call() -> object:
        return await build_server().call_tool(
            "videoflow_list_capabilities", {"allow_external_services": True}
        )

    result = asyncio.run(call())
    structured = result.structured_content  # type: ignore[attr-defined]
    assert structured["ok"] is True
    assert structured["external_services_allowed"] is True
    ids = {item["id"] for item in structured["capabilities"]}
    assert "shorts_aspects" in ids
    assert "external_llm" in ids
