from __future__ import annotations

from pathlib import Path

from videoflow.application import llm_factory


class SequenceClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.prompts: list[str] = []

    def complete_json(self, prompt: str, schema_name: str):
        self.prompts.append(prompt)
        return self.payloads.pop(0) if self.payloads else {"message": "done", "actions": []}


def test_assistant_reads_then_proposes_an_approved_edit(monkeypatch, tmp_path: Path) -> None:
    from tests.contract.test_api_timeline import _client, _job

    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    fake = SequenceClient(
        [
            {
                "message": "Checking the cut.",
                "actions": [{"tool": "get_timeline", "arguments": {}}],
                "requires_approval": False,
            },
            {
                "message": "I will shorten the first clip.",
                "actions": [
                    {
                        "tool": "apply_timeline_edits",
                        "arguments": {
                            "edits": [
                                {
                                    "clip_id": "v1",
                                    "action": "trim",
                                    "start_sec": 0.0,
                                    "end_sec": 0.5,
                                }
                            ]
                        },
                    }
                ],
                "requires_approval": True,
            },
        ]
    )
    monkeypatch.setattr(llm_factory, "build_llm", lambda: fake)

    response = client.post(f"/api/v1/jobs/{job.job_id}/assistant", json={"prompt": "shorten it"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(fake.prompts) == 2
    assert payload["requires_approval"] is True
    assert payload["approval_id"].startswith("approval-")
    assert payload["diff"][0]["clip_id"] == "v1"
    assert payload["diff"][0]["change"] == "modified"

    untouched = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    assert untouched["revision"] == 1

    approved = client.post(
        f"/api/v1/jobs/{job.job_id}/assistant/approve",
        json={"approval_id": payload["approval_id"]},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["results"][0]["applied"] is True

    changed = client.get(f"/api/v1/jobs/{job.job_id}/timeline").json()
    assert changed["revision"] == 2
    history = client.get(f"/api/v1/jobs/{job.job_id}/assistant/history").json()
    assert history["history"][-1]["applied"] is True

    replay = client.post(
        f"/api/v1/jobs/{job.job_id}/assistant/approve",
        json={"approval_id": payload["approval_id"]},
    )
    assert replay.status_code == 409


def test_assistant_rejects_unknown_tools(monkeypatch, tmp_path: Path) -> None:
    from tests.contract.test_api_timeline import _client, _job

    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    fake = SequenceClient([{"message": "bad", "actions": [{"tool": "rm_rf", "arguments": {}}]}])
    monkeypatch.setattr(llm_factory, "build_llm", lambda: fake)
    response = client.post(f"/api/v1/jobs/{job.job_id}/assistant", json={"prompt": "do it"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "state_not_ready"


def test_assistant_read_tools_and_preview_approval(monkeypatch, tmp_path: Path) -> None:
    from tests.contract.test_api_timeline import _client, _job
    from videoflow.application.previews import PreviewState

    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    fake = SequenceClient(
        [
            {
                "message": "Reading.",
                "actions": [
                    {"tool": "get_job", "arguments": {}},
                    {"tool": "list_recipes", "arguments": {}},
                    {"tool": "list_projects", "arguments": {}},
                    {"tool": "validate_exports", "arguments": {}},
                ],
                "requires_approval": False,
            },
            {
                "message": "Rendering a preview.",
                "actions": [{"tool": "render_preview", "arguments": {}}],
                "requires_approval": True,
            },
        ]
    )
    monkeypatch.setattr(llm_factory, "build_llm", lambda: fake)
    response = client.post(f"/api/v1/jobs/{job.job_id}/assistant", json={"prompt": "inspect"})
    assert response.status_code == 200, response.text
    assert response.json()["requires_approval"] is True
    observations = response.json()["observations"]
    assert {item["tool"] for item in observations} == {"a1", "a2", "a3", "a4"}

    from videoflow.api import routes as routes_module

    state = PreviewState(job_id=str(job.job_id), status="queued")
    monkeypatch.setattr(routes_module.previews, "start", lambda item: state)
    approved = client.post(
        f"/api/v1/jobs/{job.job_id}/assistant/approve",
        json={"approval_id": response.json()["approval_id"]},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["results"][0]["preview"]["status"] == "queued"


def test_assistant_run_recipe_and_corrupt_context(monkeypatch, tmp_path: Path) -> None:
    from tests.contract.test_api_timeline import _client, _job

    client, manager = _client(monkeypatch, tmp_path)
    job = _job(manager, tmp_path)
    fake = SequenceClient(
        [
            {
                "message": "Run it.",
                "actions": [
                    {
                        "tool": "run_recipe",
                        "arguments": {
                            "recipe_id": "youtube_talking_head",
                            "source": str(tmp_path / "source.mp4"),
                            "output": str(tmp_path / "assistant-out"),
                        },
                    }
                ],
                "requires_approval": True,
            }
        ]
    )
    monkeypatch.setattr(llm_factory, "build_llm", lambda: fake)
    planned = client.post(f"/api/v1/jobs/{job.job_id}/assistant", json={"prompt": "run it"})
    assert planned.status_code == 200, planned.text
    assert planned.json()["requires_approval"] is True
    approved = client.post(
        f"/api/v1/jobs/{job.job_id}/assistant/approve",
        json={"approval_id": planned.json()["approval_id"]},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["results"][0]["ok"] is True

    corrupt, corrupt_manager = _client(monkeypatch, tmp_path / "corrupt")
    corrupt_job = _job(corrupt_manager, tmp_path / "corrupt")
    (corrupt_job.output / "project_state.json").write_text("{bad", encoding="utf-8")
    read = SequenceClient(
        [
            {
                "message": "Listing.",
                "actions": [{"tool": "list_projects", "arguments": {}}],
                "requires_approval": False,
            },
            {"message": "Done.", "actions": [], "requires_approval": False},
        ]
    )
    monkeypatch.setattr(llm_factory, "build_llm", lambda: read)
    listed = corrupt.post(f"/api/v1/jobs/{corrupt_job.job_id}/assistant", json={"prompt": "list"})
    assert listed.status_code == 200, listed.text
