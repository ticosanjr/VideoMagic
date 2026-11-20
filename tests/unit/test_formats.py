from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videoflow.api.app import create_app
from videoflow.application.format_catalog import FormatCatalog
from videoflow.domain.errors import InvalidConfigError
from videoflow.domain.formats import FormatDefinition


def test_format_catalog_seeds_and_crud(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    catalog = FormatCatalog()
    items = catalog.list_payload()
    assert {item["format_id"] for item in items} >= {
        "vertical_9_16",
        "feed_4_5",
        "square_1_1",
        "landscape_16_9",
    }
    custom = catalog.duplicate("vertical_9_16", "custom_short", name="Custom Short")
    assert custom.width == 1080
    assert catalog.get("custom_short").name == "Custom Short"
    assert catalog.delete("custom_short") is True
    try:
        catalog.delete("vertical_9_16")
    except InvalidConfigError:
        pass
    else:
        raise AssertionError("built-in format delete must fail")


def test_format_definition_rejects_bad_aspect() -> None:
    try:
        FormatDefinition(
            format_id="bad",
            name="Bad",
            aspect_ratio="9:16",
            width=1920,
            height=1080,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched aspect must fail")


def test_format_routes_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    client = TestClient(create_app())
    listed = client.get("/api/v1/formats")
    assert listed.status_code == 200
    assert listed.json()["formats"]

    created = client.post(
        "/api/v1/formats",
        json={
            "format_id": "api_format",
            "name": "API format",
            "aspect_ratio": "1:1",
            "width": 1080,
            "height": 1080,
            "fps": 30,
            "caption_preset": "youtube_bold_yellow",
            "safe_zones": {"bottom_px": 120, "right_px": 60},
            "platforms": ["instagram_feed"],
            "export_targets": ["mp4_short"],
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["format"]["format_id"] == "api_format"

    duplicated = client.post(
        "/api/v1/formats/api_format/duplicate",
        json={"new_id": "api_format_2", "name": "API format 2"},
    )
    assert duplicated.status_code == 200
    assert duplicated.json()["format"]["format_id"] == "api_format_2"

    assert client.delete("/api/v1/formats/api_format").json()["deleted"] is True


def test_vf_format_tool_crud(tmp_path: Path, monkeypatch) -> None:
    from videoflow.mcp_server.format_tools import register_format_tools

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    tools = {}

    def register(func):
        tools[func.__name__] = func
        return func

    register_format_tools(register)
    listed = tools["vf_format"](action="list")
    assert listed["ok"] is True
    saved = tools["vf_format"](
        action="create",
        format_id="tool_format",
        name="Tool format",
        aspect_ratio="4:5",
        width=1080,
        height=1350,
        caption_preset="youtube_bold_yellow",
    )
    assert saved["ok"] is True
    duplicated = tools["vf_format"](
        action="duplicate", format_id="tool_format", new_id="tool_format_2"
    )
    assert duplicated["ok"] is True
    assert tools["vf_format"](action="delete", format_id="tool_format_2")["deleted"] is True
    assert tools["vf_format"](action="bogus")["code"] == "unknown_action"
