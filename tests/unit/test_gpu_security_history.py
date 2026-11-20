from __future__ import annotations

import io
import sys
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[2] / "packages" / "gpu-worker" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from fastapi.testclient import TestClient  # noqa: E402
from gpu_worker.app import create_app  # noqa: E402
from gpu_worker.artifacts import ArtifactStore  # noqa: E402
from gpu_worker.settings import Settings  # noqa: E402
from gpu_worker.store import JobStore  # noqa: E402


def _settings(tmp_path: Path, **updates) -> Settings:
    base = dict(
        token="secret",
        work_dir=tmp_path / "worker",
        max_upload_mb=2,
        max_queue=4,
        model_ttl_sec=60.0,
    )
    base.update(updates)
    return Settings(**base)


def test_token_only_rejects_private_lan_without_token(tmp_path: Path) -> None:
    app = create_app(
        _settings(tmp_path, allow_lan_open=True, token_only=True)
    )
    try:
        with TestClient(app, client=("192.168.1.50", 50000)) as client:
            assert client.get("/api/jobs").status_code == 401
            assert (
                client.get("/api/jobs", headers={"X-VF-Token": "secret"}).status_code
                == 200
            )
    finally:
        app.state.close()


def test_allowlist_limits_lan_open(tmp_path: Path) -> None:
    app = create_app(
        _settings(
            tmp_path,
            allow_lan_open=True,
            allowed_clients=("192.168.1.50/32",),
        )
    )
    try:
        with TestClient(app, client=("192.168.1.51", 50000)) as client:
            assert client.get("/api/jobs").status_code == 401
        with TestClient(app, client=("192.168.1.50", 50000)) as client:
            assert client.get("/api/jobs").status_code == 200
    finally:
        app.state.close()


def test_token_rotation_invalidates_the_old_token(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, allow_lan_open=False))
    try:
        with TestClient(app, client=("127.0.0.1", 50000)) as local:
            rotated = local.post("/api/token/rotate")
            assert rotated.status_code == 200, rotated.text
            new_token = rotated.json()["token"]
        with TestClient(app, client=("192.168.1.50", 50000)) as remote:
            assert (
                remote.get("/api/jobs", headers={"X-VF-Token": "secret"}).status_code
                == 401
            )
            assert (
                remote.get(
                    "/api/jobs", headers={"X-VF-Token": new_token}
                ).status_code
                == 200
            )
        with TestClient(app, client=("127.0.0.1", 50000)) as local:
            audit = local.get("/api/audit")
            assert audit.status_code == 200
            assert any(
                entry["outcome"] == "rotated" for entry in audit.json()["entries"]
            )
            security = local.get("/api/security")
            assert security.status_code == 200
            assert security.json()["token_file"].endswith("worker.token")
    finally:
        app.state.close()


def test_history_metrics_and_system_payloads(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    try:
        app.state.store.record_metric(
            job_id="job-1",
            capability="asr",
            status="succeeded",
            priority=3,
            queue_wait_sec=1.5,
            elapsed_sec=2.5,
        )
        with TestClient(app, client=("127.0.0.1", 50000)) as client:
            history = client.get("/api/history")
            assert history.status_code == 200
            payload = history.json()
            assert payload["metrics"][0]["job_id"] == "job-1"
            assert len(payload["samples"]) >= 1
            system = client.get("/api/system")
            assert system.status_code == 200
            assert "firewall" in system.json()
            assert "clients" in system.json()
    finally:
        app.state.close()


def test_artifact_cleanup_removes_unreferenced_objects(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "store.sqlite")
    store.initialize()
    artifacts = ArtifactStore(tmp_path / "objects", store, max_bytes=1024)
    saved = artifacts.save_upload(io.BytesIO(b"payload"), "clip.bin")
    assert artifacts.cleanup({saved.id}) == 0
    assert artifacts.get(saved.id) is not None
    assert artifacts.cleanup(set()) == 1
    assert artifacts.get(saved.id) is None


def test_local_subnets_honors_private_cidrs(monkeypatch) -> None:
    from vf_compute import discovery

    monkeypatch.setenv(
        "VF_GPU_SCAN_CIDRS",
        "10.1.0.0/28, 192.168.1.0/30, 8.8.8.0/24",
    )
    assert discovery.local_subnets(force=True) == ["10.1.0.0/28", "192.168.1.0/30"]
