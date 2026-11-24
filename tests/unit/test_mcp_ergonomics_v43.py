from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from videoflow.mcp_server.core_tools.core_jobs import _distribute_params
from videoflow.mcp_server.guard import error_envelope
from videoflow.mcp_server.registry import CORE_TOOL_NAMES


def test_step_params_are_distributed_and_unknown_keys_fail() -> None:
    distributed, invalid = _distribute_params(
        ["timeline.load", "shorts.select"],
        {"count": 2, "aspect_ratio": "9:16"},
        None,
    )
    assert distributed == {
        "shorts.select": {"count": 2, "aspect_ratio": "9:16"}
    }
    assert invalid == []

    _distributed, invalid = _distribute_params(
        ["timeline.load"],
        {"not_a_real_field": 1},
        None,
    )
    assert invalid == ["not_a_real_field"]


def test_vf_run_forwards_only_matching_params(monkeypatch, tmp_path: Path) -> None:
    from tests.unit.test_core_tools import setup

    tools, record, _job = setup(tmp_path, monkeypatch)
    result = tools["vf_run"](
        project_id=record.project_id,
        steps=["timeline.load", "shorts.select"],
        params={"count": 2, "aspect_ratio": "9:16"},
        wait=False,
    )
    assert result["ok"] is True
    assert result["step_params"] == {
        "shorts.select": {"count": 2, "aspect_ratio": "9:16"}
    }

    invalid = tools["vf_run"](
        project_id=record.project_id,
        steps=["timeline.load"],
        params={"definitely_not_a_field": True},
        wait=False,
    )
    assert invalid["code"] == "invalid_params"


def test_vf_jobs_wait_returns_flat_payload(monkeypatch, tmp_path: Path) -> None:
    from tests.unit.test_core_tools import setup

    tools, record, job = setup(tmp_path, monkeypatch)
    job.result = {"artifacts": {"mp4": "out.mp4"}}
    waited = tools["vf_job"](
        action="wait", project_id=record.project_id, job_id="job-1"
    )
    assert waited["ok"] is True
    assert waited["job_id"] == "job-1"
    assert waited["status"] == "succeeded"
    assert waited["result"] == {"artifacts": {"mp4": "out.mp4"}}
    assert waited["error"] is None
    assert waited["artifacts"]


def test_project_create_alias_defaults_output_and_resolves_uuid(
    monkeypatch, tmp_path: Path
) -> None:
    from tests.unit.test_agent_mcp import call
    from videoflow.mcp_server.server import build_server

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    server = build_server()
    created = call(
        server,
        "vf_project",
        {"action": "create", "project_id": "paula-ep-10"},
    )
    assert created["ok"] is True
    assert created["project"]["project_id"] == "paula-ep-10"
    assert created["uuid"]
    assert Path(created["project"]["output"]).name == "paula-ep-10"
    status = call(
        server,
        "vf_project",
        {"action": "status", "project_id": created["uuid"]},
    )
    assert status["ok"] is True
    assert status["project"]["project_id"] == "paula-ep-10"


def test_validation_error_exposes_expected_fields() -> None:
    class Payload(BaseModel):
        count: int

    def demo_tool(project_id: str, count: int) -> None:
        return None

    with pytest.raises(ValidationError) as captured:
        Payload(count="not-an-int")
    envelope = error_envelope(captured.value, func=demo_tool)
    assert envelope["code"] == "invalid_params"
    assert envelope["expected_fields"] == {
        "project_id": "str",
        "count": "int",
    }
    assert "project_id" in envelope["fix_hint"]


def test_style_is_exposed_in_core() -> None:
    assert "vf_style" in CORE_TOOL_NAMES
    assert len(CORE_TOOL_NAMES) == 18


def test_canonical_project_id_resolves_slug_uuid_and_output_folder(
    monkeypatch, tmp_path: Path
) -> None:
    from videoflow.application.projects import (
        ProjectStateError,
        canonical_project_id,
        init_project,
        project_uuid,
        resolve_project_ref,
    )

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    init_project(
        name="Episode",
        output=tmp_path / "episode",
        project_id="paula-ep-10",
    )
    uuid = str(project_uuid("paula-ep-10"))
    assert canonical_project_id(uuid) == "paula-ep-10"
    assert canonical_project_id("paula-ep-10") == "paula-ep-10"
    assert canonical_project_id("episode") == "paula-ep-10"
    assert canonical_project_id("Episode") == "Episode"
    assert canonical_project_id("unknown-project") == "unknown-project"
    with pytest.raises(ProjectStateError):
        resolve_project_ref("Episode")


def test_guard_canonicalizes_uuid_before_the_tool_body(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application.projects import init_project, project_uuid
    from videoflow.mcp_server.guard import mcp_tool_guard

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    init_project(
        name="Episode",
        output=tmp_path / "episode",
        project_id="paula-ep-10",
    )
    seen: list[str] = []

    def demo_tool(project_id: str) -> dict[str, object]:
        seen.append(project_id)
        return {"ok": True, "project_id": project_id}

    guarded = mcp_tool_guard(demo_tool)
    result = guarded(project_id=str(project_uuid("paula-ep-10")))
    assert result["ok"] is True
    assert seen == ["paula-ep-10"]


def test_server_resolves_uuid_for_session_brief(monkeypatch, tmp_path: Path) -> None:
    from tests.unit.test_agent_mcp import call
    from videoflow.mcp_server.server import build_server

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    server = build_server()
    created = call(
        server,
        "vf_project",
        {"action": "create", "project_id": "paula-ep-10"},
    )
    assert created["ok"] is True
    brief = call(server, "vf_session_brief", {"project_id": created["uuid"]})
    assert brief["ok"] is True
    assert brief["project_id"] == "paula-ep-10"
