"""P0-1: content-addressed artifact cache and strict heavy offload."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from vf_shared.compute.client import GPUWorkerAuthError, GPUWorkerClient
from vf_shared.compute.models import WorkerHealth
from vf_shared.compute.router import ComputeRouter

PACKAGE_SRC = Path(__file__).resolve().parents[2] / "packages" / "gpu-worker" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from gpu_worker.app import create_app  # noqa: E402
from gpu_worker.settings import Settings  # noqa: E402

TOKEN = "test-token"
HEADERS = {"X-VF-Token": TOKEN}


@pytest.fixture
def worker(tmp_path: Path):
    application = create_app(
        Settings(token=TOKEN, work_dir=tmp_path / "worker", max_upload_mb=1)
    )
    try:
        with TestClient(application) as client:
            yield client
    finally:
        application.state.close()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_head_artifact_hits_and_misses(worker: TestClient) -> None:
    content = b"cache-me"
    uploaded = worker.post(
        "/artifacts",
        files={"file": ("clip.wav", content, "application/octet-stream")},
        headers=HEADERS,
    )
    assert uploaded.status_code == 200, uploaded.text
    artifact_id = uploaded.json()["artifact_id"]

    hit = worker.head(f"/artifacts/{artifact_id}", headers=HEADERS)
    assert hit.status_code == 200
    assert hit.headers["X-VF-Artifact-Id"] == artifact_id

    miss = worker.head(f"/artifacts/{_sha(b'missing')}", headers=HEADERS)
    assert miss.status_code == 404

    invalid = worker.head("/artifacts/not-a-sha", headers=HEADERS)
    assert invalid.status_code == 400

    denied = worker.head(f"/artifacts/{artifact_id}")
    assert denied.status_code == 401


def test_client_skips_upload_when_head_hits(tmp_path: Path) -> None:
    source = tmp_path / "clip.wav"
    source.write_bytes(b"same-bytes")
    digest = _sha(source.read_bytes())
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        assert request.method == "HEAD"
        return httpx.Response(200, headers={"X-VF-Artifact-Id": digest})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = GPUWorkerClient(
        "http://worker.test", token=TOKEN, http_client=http
    )
    assert client.upload_artifact(source) == digest
    assert calls == ["HEAD"]
    assert client.transfer_stats["upload_dedup"] == 1


def test_client_falls_back_to_init_for_old_worker(tmp_path: Path) -> None:
    source = tmp_path / "clip.wav"
    source.write_bytes(b"new-bytes")
    digest = _sha(source.read_bytes())
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "HEAD":
            return httpx.Response(404)
        assert request.url.path == "/artifacts/init"
        return httpx.Response(
            200,
            json={
                "upload_id": "",
                "artifact_id": digest,
                "complete": True,
                "sha256": digest,
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = GPUWorkerClient(
        "http://worker.test", token=TOKEN, http_client=http
    )
    assert client.upload_artifact(source) == digest
    assert ("HEAD", f"/artifacts/{digest}") in calls
    assert ("POST", "/artifacts/init") in calls


def test_client_reports_auth_failure_instead_of_offline(tmp_path: Path) -> None:
    source = tmp_path / "clip.wav"
    source.write_bytes(b"secret")
    http = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(401))
    )
    client = GPUWorkerClient(
        "http://worker.test", token="wrong", http_client=http
    )
    with pytest.raises(GPUWorkerAuthError) as info:
        client.upload_artifact(source)
    assert info.value.code == "gpu_worker_auth_failed"
    assert info.value.status_code == 401


class _SaturatedClient:
    def health(self, timeout: float | None = None) -> WorkerHealth:
        return WorkerHealth(
            available=True,
            worker_id="worker-1",
            vram_free_mb=0,
            vram_total_mb=12288,
            queue_depth=99,
            gpu_utilization=100,
            capabilities=["asr", "short_render", "ingest_pcm", "audio_finalize"],
        )


def test_heavy_offload_ignores_worker_saturation() -> None:
    router = ComputeRouter(
        client=_SaturatedClient(),
        min_vram_mb=4096,
        max_queue=0,
        max_gpu_utilization=1.0,
        offload_all_heavy=True,
    )
    assert router.decide("asr").is_remote is True
    assert router.decide("short_render").is_remote is True
    assert router.decide("ingest_pcm").is_remote is True
    assert router.decide("audio_finalize").is_remote is True


def test_old_settings_enable_new_heavy_capabilities() -> None:
    from videoflow.application.schema_migrations import migrate_settings

    migrated = migrate_settings(
        {"gpu": {"capabilities": {"asr": True, "render_nvenc": True}}}
    )
    capabilities = migrated["gpu"]["capabilities"]
    assert capabilities["ingest_pcm"] is True
    assert capabilities["audio_finalize"] is True


def test_changed_file_gets_a_new_hash_and_misses(tmp_path: Path) -> None:
    source = tmp_path / "clip.wav"
    source.write_bytes(b"first")
    first_digest = _sha(source.read_bytes())
    source.write_bytes(b"second")
    second_digest = _sha(source.read_bytes())
    assert first_digest != second_digest

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(first_digest):
            return httpx.Response(200, headers={"X-VF-Artifact-Id": first_digest})
        return httpx.Response(404)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = GPUWorkerClient("http://worker.test", http_client=http)
    assert client.probe_artifact(first_digest) == first_digest
    assert client.probe_artifact(second_digest) is None
