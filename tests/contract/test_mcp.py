import asyncio
import json

from videoflow.mcp_server.registry import RESOURCE_SPECS, TOOL_SPECS
from videoflow.mcp_server.server import build_server


def test_registry_names_are_unique_and_prefixed() -> None:
    names = [tool.name for tool in TOOL_SPECS]
    assert len(names) == len(set(names))
    assert all(name.startswith("videoflow_") for name in names)
    assert len(RESOURCE_SPECS) == 5


def test_server_registers_every_public_tool() -> None:
    async def inspect() -> list[str]:
        return [tool.name for tool in await build_server().list_tools()]

    assert sorted(asyncio.run(inspect())) == sorted(tool.name for tool in TOOL_SPECS)


def test_server_uses_the_registry_as_its_public_descriptions() -> None:
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


def test_tools_without_media_return_a_typed_error() -> None:
    async def call() -> object:
        return await build_server().call_tool(
            "videoflow_run_recipe", {"recipe_id": "youtube_talking_head"}
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
    assert "shorts-aggressive.json" in payload["presets"]


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


def test_new_job_and_cost_tools_are_callable() -> None:
    async def call(name: str, arguments: dict[str, object]) -> dict[str, object]:
        result = await build_server().call_tool(name, arguments)
        return result.structured_content  # type: ignore[attr-defined]

    jobs = asyncio.run(call("videoflow_list_jobs", {}))
    cost = asyncio.run(call("videoflow_cost_metrics", {}))
    timeline = asyncio.run(call("videoflow_get_timeline", {}))
    assert jobs["ok"] is True
    assert cost["ok"] is True
    assert timeline["ok"] is False
    assert timeline["code"] == "state_not_ready"


def test_integrations_resource_lists_opencode_and_paperclip() -> None:
    async def read() -> str:
        contents = await build_server().read_resource("videoflow://docs/integrations")
        return next(iter(contents)).content  # type: ignore[attr-defined]

    payload = json.loads(asyncio.run(read()))
    assert payload["opencode"]["model"] == "deepseek/deepseek-flash"
    assert payload["paperclip"]["mcp_url"].endswith("/mcp/")


def test_tools_carry_behavior_annotations() -> None:
    async def inspect() -> dict[str, object]:
        tools = await build_server().list_tools()
        return {tool.name: tool.annotations for tool in tools}

    annotations = asyncio.run(inspect())
    assert annotations["videoflow_get_timeline"].read_only_hint is True
    assert annotations["videoflow_cancel_job"].destructive_hint is True
    assert annotations["videoflow_save_recipe"].idempotent_hint is True
    assert annotations["videoflow_import_url"].open_world_hint is True


def test_mcp_exposes_production_prompts() -> None:
    async def inspect() -> list[str]:
        prompts = await build_server().list_prompts()
        return [prompt.name for prompt in prompts]

    assert asyncio.run(inspect()) == [
        "videoflow_produce",
        "videoflow_review",
        "videoflow_deliver",
    ]


def test_list_tools_paginate() -> None:
    async def call(name: str, arguments: dict[str, object]) -> dict[str, object]:
        result = await build_server().call_tool(name, arguments)
        return result.structured_content  # type: ignore[attr-defined]

    recipes = asyncio.run(call("videoflow_list_recipes", {"limit": 2, "offset": 0}))
    assert recipes["ok"] is True
    assert len(recipes["recipes"]) == 2
    assert recipes["total"] >= 2
    steps = asyncio.run(call("videoflow_list_steps", {"limit": 3}))
    assert len(steps["steps"]) == 3
