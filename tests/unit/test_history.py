from pathlib import Path

from fastapi.testclient import TestClient

from videoflow.api.app import create_app
from videoflow.engine.history import append_run, read_runs


def test_history_appends_and_reads(tmp_path: Path) -> None:
    output = tmp_path / "out"
    append_run(
        output,
        {
            "job_id": "a",
            "status": "succeeded",
            "recipe_id": "recipe",
            "created_at": "2026-01-01T00:00:00Z",
            "step_runs": [],
            "warnings": [],
        },
    )
    append_run(
        output,
        {
            "job_id": "b",
            "status": "succeeded",
            "recipe_id": "recipe",
            "created_at": "2026-01-01T00:01:00Z",
            "step_runs": [],
            "warnings": [],
        },
    )
    assert [item["job_id"] for item in read_runs(output)] == ["a", "b"]


def test_history_api_reads_an_output(tmp_path: Path) -> None:
    home = tmp_path / "videoflow-home"
    output = home / "out"
    append_run(output, {"job_id": "a", "status": "succeeded", "recipe_id": "recipe"})
    client = TestClient(create_app())
    response = client.get("/api/v1/runs", params={"output": str(output)})
    assert response.status_code == 200
    assert response.json()["runs"][0]["job_id"] == "a"


def test_history_paginates(tmp_path: Path) -> None:
    from videoflow.engine.history import read_runs

    for index in range(5):
        append_run(tmp_path, {"job_id": str(index), "status": "succeeded"})
    assert [item["job_id"] for item in read_runs(tmp_path, limit=2, offset=1)] == [
        "1",
        "2",
    ]
