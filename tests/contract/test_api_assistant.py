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

    response = client.post(
        f"/api/v1/jobs/{job.job_id}/assistant", json={"prompt": "shorten it"}
    )
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
    fake = SequenceClient(
        [{"message": "bad", "actions": [{"tool": "rm_rf", "arguments": {}}]}]
    )
    monkeypatch.setattr(llm_factory, "build_llm", lambda: fake)
    response = client.post(
        f"/api/v1/jobs/{job.job_id}/assistant", json={"prompt": "do it"}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "state_not_ready"
