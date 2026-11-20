import asyncio
import json
import uuid

from videoflow.mcp_server.registry import RESOURCE_SPECS, TOOL_SPECS
from videoflow.mcp_server.server import build_server


def test_registry_is_the_core_profile() -> None:
    names = [tool.name for tool in TOOL_SPECS]
    assert len(names) == 35
    assert len(names) == len(set(names))
    assert all(name.startswith("vf_") for name in names)
    assert len(RESOURCE_SPECS) == 16


def test_server_registers_every_public_tool() -> None:
    async def inspect() -> list[str]:
        return [tool.name for tool in await build_server().list_tools()]

    assert sorted(asyncio.run(inspect())) == sorted(tool.name for tool in TOOL_SPECS)


def test_server_uses_the_registry_descriptions() -> None:
    async def inspect() -> dict[str, str]:
        tools = await build_server().list_tools()
        return {tool.name: tool.description or "" for tool in tools}

    descriptions = asyncio.run(inspect())
    for spec in TOOL_SPECS:
        assert descriptions[spec.name] == spec.description


def test_every_tool_has_annotations() -> None:
    async def inspect() -> dict[str, object]:
        tools = await build_server().list_tools()
        return {tool.name: tool.annotations for tool in tools}

    annotations = asyncio.run(inspect())
    assert len(annotations) == len(TOOL_SPECS)
    assert all(value is not None for value in annotations.values())


def test_unknown_project_returns_a_typed_error() -> None:
    async def call() -> object:
        return await build_server().call_tool("vf_timeline", {"project_id": str(uuid.uuid4())})

    structured = asyncio.run(call()).structured_content  # type: ignore[attr-defined]
    assert structured["ok"] is False
    assert structured["code"] in {"project_state_invalid", "project_not_found"}


def test_missing_state_resource_reports_a_typed_error() -> None:
    async def read(uri: str) -> str:
        contents = await build_server().read_resource(uri)
        return next(iter(contents)).content  # type: ignore[attr-defined]

    project_id = str(uuid.uuid4())
    state = json.loads(asyncio.run(read(f"vf://projects/{project_id}/state")))
    assert state["ok"] is False
    assert state["code"] in {"project_state_invalid", "project_not_found"}


def test_capabilities_tool_reports_policy() -> None:
    async def call() -> object:
        return await build_server().call_tool("vf_capabilities", {"allow_external_services": True})

    structured = asyncio.run(call()).structured_content  # type: ignore[attr-defined]
    assert structured["ok"] is True
    ids = {item["id"] for item in structured["capabilities"]}
    assert "shorts_aspects" in ids


def test_step_docs_resource_exposes_parameters() -> None:
    async def read() -> str:
        contents = await build_server().read_resource("vf://docs/steps/session.ingest")
        return next(iter(contents)).content  # type: ignore[attr-defined]

    payload = json.loads(asyncio.run(read()))
    assert payload["type"] == "session.ingest"
    assert "sources" in payload["schema"]["properties"]


def test_tools_carry_behavior_annotations() -> None:
    async def inspect() -> dict[str, object]:
        tools = await build_server().list_tools()
        return {tool.name: tool.annotations for tool in tools}

    annotations = asyncio.run(inspect())
    assert annotations["vf_capabilities"].read_only_hint is True
    assert annotations["vf_catalog_search"].read_only_hint is True


def test_mcp_exposes_production_prompts() -> None:
    async def inspect() -> list[str]:
        prompts = await build_server().list_prompts()
        return [prompt.name for prompt in prompts]

    assert asyncio.run(inspect()) == [
        "videoflow_produce",
        "videoflow_review",
        "videoflow_deliver",
    ]


def test_mcp_surface_has_no_recipe_tools_or_resources() -> None:
    assert not [spec for spec in TOOL_SPECS if "recipe" in spec.name]
    assert not [spec for spec in RESOURCE_SPECS if "recipe" in spec.uri]


def test_step_catalog_resource_lists_all_nodes() -> None:
    async def read() -> str:
        contents = await build_server().read_resource("vf://docs/steps")
        return next(iter(contents)).content  # type: ignore[attr-defined]

    payload = json.loads(asyncio.run(read()))
    assert payload["ok"] is True
    assert len(payload["steps"]) > 100
    assert any(item["type"] == "session.ingest" for item in payload["steps"])


def test_catalog_search_paginates_steps() -> None:
    async def call(offset: int) -> dict:
        result = await build_server().call_tool("vf_catalog_search", {"offset": offset, "limit": 5})
        return result.structured_content  # type: ignore[attr-defined]

    first = asyncio.run(call(0))
    second = asyncio.run(call(5))
    assert len(first["steps"]) == 5
    assert len(second["steps"]) == 5
    assert first["next_offset"] == 5
    assert first["steps"][0]["type"] != second["steps"][0]["type"]
    assert "recipes" not in first
