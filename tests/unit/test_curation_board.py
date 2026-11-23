"""P0-2: visual curation board, REST routes, and vf_curation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videoflow.api.app import create_app
from videoflow.application.curation_board import (
    CurationError,
    auto_select_board,
    list_pending_boards,
    load_decisions,
    publish_board,
    save_decisions,
)
from videoflow.application.projects import init_project
from videoflow.mcp_server.server import build_server


def _items() -> list[dict[str, object]]:
    return [
        {
            "item_id": "music-1",
            "category": "music",
            "scene_id": "scene-1",
            "title": "Bed A",
            "media_type": "audio",
            "recommended": True,
        },
        {
            "item_id": "sfx-1",
            "category": "sfx",
            "scene_id": "scene-1",
            "title": "Whoosh",
            "media_type": "audio",
        },
        {
            "item_id": "broll-1",
            "category": "broll",
            "scene_id": "scene-2",
            "title": "City",
            "media_type": "video",
        },
    ]


@pytest.fixture
def project(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    record, _ = init_project(output=tmp_path / "project")
    return record


def test_publish_human_decision_and_pending_list(project, tmp_path: Path) -> None:
    board = publish_board(project.output, project.project_id, _items())
    assert board.status == "waiting_human"
    assert (Path(project.output) / "curation" / "board.json").is_file()
    assert (Path(project.output) / "curation" / "decisions.json").is_file()
    assert len(list_pending_boards(tmp_path)) == 1

    updated = save_decisions(
        project.output,
        selected_ids=["sfx-1"],
        rejected_ids=["music-1"],
    )
    assert updated.status == "decided"
    by_id = {item.item_id: item for item in updated.items}
    assert by_id["sfx-1"].status == "selected"
    assert by_id["music-1"].status == "rejected"
    assert by_id["broll-1"].status == "pending"
    decisions = load_decisions(project.output)
    assert decisions is not None
    assert decisions.selected_ids == ["sfx-1"]
    assert decisions.rejected_ids == ["music-1"]
    assert list_pending_boards(tmp_path) == []
    client = TestClient(create_app())
    listed = client.get("/api/v1/curation/boards").json()["boards"]
    assert listed[0]["status"] == "decided"
    pending = client.get(
        "/api/v1/curation/boards", params={"pending_only": True}
    ).json()["boards"]
    assert pending == []


def test_delegate_and_auto_select(project) -> None:
    publish_board(project.output, project.project_id, _items())
    delegated = save_decisions(project.output, [], [], delegate_to_ai=True)
    assert delegated.status == "delegated_to_ai"
    assert [item.item_id for item in delegated.items if item.status == "selected"] == [
        "music-1"
    ]

    items = _items()
    for item in items:
        item["recommended"] = False
    publish_board(project.output, project.project_id, items)
    automatic = auto_select_board(project.output)
    selected = [item.item_id for item in automatic.items if item.status == "selected"]
    assert selected == ["music-1", "sfx-1", "broll-1"]


def test_empty_and_duplicate_boards_fail_closed(project) -> None:
    with pytest.raises(CurationError) as empty:
        publish_board(project.output, project.project_id, [])
    assert empty.value.code == "empty_curation_board"

    duplicate = _items() + [_items()[0]]
    with pytest.raises(CurationError) as duplicated:
        publish_board(project.output, project.project_id, duplicate)
    assert duplicated.value.code == "duplicate_item_id"


def test_api_media_path_traversal_is_blocked(
    project, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(project.output))
    allowed = Path(project.output) / "clip.wav"
    allowed.write_bytes(b"audio")
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"audio")
    items = _items()
    items[0]["local_path"] = str(allowed)
    items[1]["local_path"] = str(outside)
    publish_board(project.output, project.project_id, items)
    client = TestClient(create_app())

    assert client.get(f"/api/v1/curation/{project.project_id}").status_code == 200
    assert (
        client.get(f"/api/v1/curation/{project.project_id}/media/music-1").status_code
        == 200
    )
    blocked = client.get(
        f"/api/v1/curation/{project.project_id}/media/sfx-1"
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "path_not_allowed"
    assert client.get("/api/v1/curation/boards").json()["boards"]


def test_api_decide_roundtrip(project) -> None:
    publish_board(project.output, project.project_id, _items())
    client = TestClient(create_app())
    response = client.post(
        f"/api/v1/curation/{project.project_id}/decide",
        json={"selected_ids": ["broll-1"], "rejected_ids": []},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["decisions"]["status"] == "decided"
    assert payload["board"]["status"] == "decided"


def test_vf_curation_two_turns(project) -> None:
    async def call(arguments: dict) -> dict:
        server = build_server(profile="core")
        result = await server.call_tool("vf_curation", arguments)
        return result.structured_content  # type: ignore[attr-defined]

    published = asyncio.run(
        call(
            {
                "action": "publish",
                "project_id": project.project_id,
                "items": _items(),
            }
        )
    )
    assert published["ok"] is True
    assert published["status"] == "waiting_human"
    assert published["item_count"] == 3
    assert "board_url" in published
    assert published["_next_step"]

    waiting = asyncio.run(
        call({"action": "read", "project_id": project.project_id})
    )
    assert waiting["status"] == "waiting_human"
    assert waiting["_next_step"]

    selected = asyncio.run(
        call({"action": "auto_select", "project_id": project.project_id})
    )
    assert selected["status"] == "delegated_to_ai"
    assert [item["item_id"] for item in selected["selected"]] == ["music-1"]
    assert selected["_next_step"]


def test_vf_curation_rejects_empty_items(project) -> None:
    async def call() -> dict:
        server = build_server(profile="core")
        result = await server.call_tool(
            "vf_curation",
            {"action": "publish", "project_id": project.project_id, "items": []},
        )
        return result.structured_content  # type: ignore[attr-defined]

    payload = asyncio.run(call())
    assert payload["ok"] is False
    assert payload["error_code"] == "empty_curation_board"
