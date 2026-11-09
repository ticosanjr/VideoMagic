from __future__ import annotations

import asyncio
import time
from pathlib import Path

from videoflow.application.jobs import JobManager
from videoflow.mcp_server.server import build_server


def call(server, name: str, arguments: dict | None = None) -> dict:
    async def run() -> dict:
        result = await server.call_tool(name, arguments or {})
        return result.structured_content  # type: ignore[attr-defined]

    return asyncio.run(run())


def _wait(manager: JobManager, job_id: str, statuses: set[str]):
    deadline = time.time() + 10
    while time.time() < deadline:
        job = manager.get(job_id)
        if job.status in statuses:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not reach {statuses}")


def test_mcp_lists_and_answers_a_hilt_request(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    manager = JobManager()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    recipe = {
        "schema_version": 1,
        "id": "mcp_hilt",
        "name": "MCP HILT",
        "steps": [
            {
                "id": "ask",
                "type": "human.input",
                "params": {
                    "gate_id": "brief",
                    "title": "Brief",
                    "questions": [{"id": "topic", "label": "Topic", "type": "text"}],
                },
            },
            {
                "id": "index",
                "type": "assets.index",
                "needs": ["ask"],
                "params": {"asset_dir": ""},
            },
        ],
    }
    job = manager.start(
        source, tmp_path / "out", {"mode": "recipe", "recipe": recipe}, queue=True
    )
    waiting = _wait(manager, str(job.job_id), {"waiting_input", "failed"})
    assert waiting.status == "waiting_input", waiting.error
    server = build_server(manager)

    listed = call(server, "videoflow_list_interactions", {"job_id": str(job.job_id)})
    assert listed["ok"] is True
    interaction = listed["interactions"][0]["interaction"]
    assert interaction["questions"][0]["id"] == "topic"

    detail = call(
        server,
        "videoflow_get_interaction",
        {"job_id": str(job.job_id), "interaction_id": interaction["interaction_id"]},
    )
    assert detail["ok"] is True

    answered = call(
        server,
        "videoflow_respond_to_interaction",
        {
            "job_id": str(job.job_id),
            "interaction_id": interaction["interaction_id"],
            "action": "submit",
            "answers": {"topic": "Corruption"},
            "comment": "ok",
        },
    )
    assert answered["ok"] is True, answered
    done = _wait(manager, answered["job"]["job_id"], {"succeeded", "failed"})
    assert done.status == "succeeded", done.error
