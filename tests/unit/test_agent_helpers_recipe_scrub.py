from pathlib import Path
from types import SimpleNamespace

from videoflow.mcp_server.agent_helpers import _job_payload


def test_job_payload_removes_recipe_documents(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    job = SimpleNamespace(
        output=output,
        result={
            "recipe_id": "demo",
            "mode": "recipe",
            "variants": [{"name": "v1", "summary": {"mode": "recipe"}}],
            "artifacts": {"audio": "a.wav"},
        },
        to_dict=lambda: {
            "job_id": "job-1",
            "options": {
                "mode": "recipe",
                "recipe": {"id": "demo", "steps": []},
                "variables": {"x": 1},
                "profile": "full",
                "step_type": "audio.mix",
            },
            "result": {
                "recipe_id": "demo",
                "mode": "recipe",
                "variants": [{"name": "v1"}],
                "artifacts": {},
            },
        },
    )

    payload = _job_payload(job)

    assert "recipe" not in payload["options"]
    assert "variables" not in payload["options"]
    assert "profile" not in payload["options"]
    assert payload["options"]["mode"] == "step"
    assert "recipe_id" not in payload["result"]
    assert "variants" not in payload["result"]
    assert payload["result"]["mode"] == "step"
    assert "variants" not in payload
