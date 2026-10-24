from pathlib import Path

from tests.contract.test_api_jobs import fake_runner, make_client, wait_http


def test_retry_creates_a_new_job_after_a_failure(tmp_path: Path, monkeypatch) -> None:
    calls = {"count": 0}

    def flaky_runner(source: Path, output: Path, *, progress, should_cancel, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("transient failure")
        return fake_runner(
            source,
            output,
            progress=progress,
            should_cancel=should_cancel,
            **kwargs,
        )

    client = make_client(monkeypatch, tmp_path, runner=flaky_runner)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    created = client.post(
        "/api/v1/jobs",
        json={"source": str(source), "output": str(tmp_path / "out"), "options": {}},
    )
    job = created.json()["job"]
    failed = wait_http(client, job["job_id"])
    assert failed["status"] == "failed"

    response = client.post(f"/api/v1/jobs/{job['job_id']}/retry")

    assert response.status_code == 202, response.text
    retried = response.json()["job"]
    assert retried["job_id"] != job["job_id"]
    assert retried["options"]["resume"] is True
    assert wait_http(client, retried["job_id"])["status"] == "succeeded"


def test_retry_rejects_finished_jobs(tmp_path: Path, monkeypatch) -> None:
    client = make_client(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    job = client.post(
        "/api/v1/jobs",
        json={"source": str(source), "output": str(tmp_path / "out"), "options": {}},
    ).json()["job"]
    wait_http(client, job["job_id"])

    response = client.post(f"/api/v1/jobs/{job['job_id']}/retry")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "state_not_ready"


def test_retry_unknown_job_is_404(tmp_path: Path, monkeypatch) -> None:
    client = make_client(monkeypatch, tmp_path)
    assert client.post("/api/v1/jobs/missing/retry").status_code == 404


def test_recipe_run_honours_the_idempotency_key(tmp_path: Path, monkeypatch) -> None:
    release = __import__("threading").Event()

    def slow_runner(source, output, *, progress, should_cancel, **kwargs):
        release.wait(timeout=5.0)
        return {"ok": True}

    client = make_client(monkeypatch, tmp_path, runner=slow_runner)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    payload = {
        "source": str(source),
        "output": str(tmp_path / "out"),
        "idempotency_key": "batch-42",
    }

    first = client.post("/api/v1/jobs", json=payload)
    second = client.post("/api/v1/jobs", json=payload)
    release.set()

    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    assert first.json()["job"]["job_id"] == second.json()["job"]["job_id"]
