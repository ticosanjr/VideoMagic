from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[2] / "packages" / "gpu-worker" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from gpu_worker import worker as worker_module  # noqa: E402
from gpu_worker.app import create_app  # noqa: E402
from gpu_worker.settings import Settings  # noqa: E402
from vf_shared.compute.client import GPUWorkerClient  # noqa: E402
from vf_shared.compute.models import JobStatus, WorkerHealth  # noqa: E402
from vf_shared.compute.router import ComputeRouter  # noqa: E402

TOKEN = "test-token"
HEADERS = {"X-VF-Token": TOKEN}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    shared_root = tmp_path / "shared"
    shared_root.mkdir()
    return Settings(
        token=TOKEN,
        work_dir=tmp_path / "worker",
        max_upload_mb=2,
        max_queue=4,
        model_ttl_sec=60.0,
        shared_root=shared_root,
    )


@pytest.fixture
def app(settings: Settings):
    application = create_app(settings)
    try:
        yield application
    finally:
        application.state.close()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def _register_handler(app, content: bytes = b"streamed-result") -> None:
    def handler(params, input_paths, work_dir):
        output = work_dir / "result.bin"
        output.write_bytes(content)
        return [output]

    app.state.registry.register_handler("fake", handler)


def _wait(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/jobs/{job_id}", headers=HEADERS)
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] in {"succeeded", "failed", "cancelled"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_worker_probe_reports_cuda_nvenc_and_matte(client: TestClient) -> None:
    response = client.post("/probe", headers=HEADERS)
    assert response.status_code == 200, response.text
    payload = response.json()
    for key in ("ok", "cuda", "nvenc", "asr", "matte", "gpu_name", "latency_ms"):
        assert key in payload
    assert isinstance(payload["cuda"], bool)
    assert isinstance(payload["nvenc"], bool)


def test_resumable_upload_resumes_and_completes(client: TestClient) -> None:
    content = b"resumable-upload-content"
    digest = hashlib.sha256(content).hexdigest()
    init = client.post(
        "/artifacts/init",
        json={
            "filename": "voice.wav",
            "size": len(content),
            "sha256": digest,
            "chunk_size": 5,
        },
        headers=HEADERS,
    )
    assert init.status_code == 200, init.text
    upload_id = init.json()["upload_id"]

    first = client.patch(
        f"/artifacts/{upload_id}",
        content=content[:5],
        headers={**HEADERS, "Content-Range": f"bytes 0-4/{len(content)}"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["received"] == 5

    resumed = client.post(
        "/artifacts/init",
        json={
            "filename": "voice.wav",
            "size": len(content),
            "sha256": digest,
            "chunk_size": 5,
        },
        headers=HEADERS,
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["upload_id"] == upload_id
    assert resumed.json()["offset"] == 5

    rest = content[5:]
    second = client.patch(
        f"/artifacts/{upload_id}",
        content=rest,
        headers={
            **HEADERS,
            "Content-Range": f"bytes 5-{len(content) - 1}/{len(content)}",
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["received"] == len(content)

    complete = client.post(f"/artifacts/{upload_id}/complete", headers=HEADERS)
    assert complete.status_code == 200, complete.text
    payload = complete.json()
    assert payload["artifact_id"] == digest
    assert payload["bytes"] == len(content)


def test_resumable_upload_rejects_bad_digest(client: TestClient) -> None:
    content = b"bad-digest"
    init = client.post(
        "/artifacts/init",
        json={
            "filename": "bad.bin",
            "size": len(content),
            "sha256": "0" * 64,
            "chunk_size": 4,
        },
        headers=HEADERS,
    )
    upload_id = init.json()["upload_id"]
    client.patch(
        f"/artifacts/{upload_id}",
        content=content,
        headers={
            **HEADERS,
            "Content-Range": f"bytes 0-{len(content) - 1}/{len(content)}",
        },
    )
    complete = client.post(f"/artifacts/{upload_id}/complete", headers=HEADERS)
    assert complete.status_code == 400
    assert "SHA-256" in complete.text


def test_worker_materializes_input_placeholders(client: TestClient, app) -> None:
    seen: dict[str, object] = {}

    def handler(params, input_paths, work_dir):
        seen["param"] = params["input"]
        seen["content"] = input_paths[0].read_bytes()
        output = work_dir / "result.bin"
        output.write_bytes(b"ok")
        return [output]

    app.state.registry.register_handler("fake", handler)
    uploaded = client.post(
        "/artifacts",
        files={"file": ("voice.wav", b"voice-bytes", "application/octet-stream")},
        headers=HEADERS,
    )
    artifact_id = uploaded.json()["artifact_id"]
    response = client.post(
        "/jobs/fake",
        json={"params": {"input": "__VF_INPUT_0__"}, "inputs": [artifact_id]},
        headers=HEADERS,
    )
    job = _wait(client, response.json()["job_id"])
    assert job["status"] == "succeeded", job
    assert str(seen["param"]).endswith("input_000.wav")
    assert seen["content"] == b"voice-bytes"


def test_manifest_head_and_range_download(client: TestClient, app) -> None:
    _register_handler(app, b"0123456789")
    response = client.post("/jobs/fake", json={}, headers=HEADERS)
    job = _wait(client, response.json()["job_id"])
    assert job["status"] == "succeeded"
    job_id = job["job_id"]

    manifest = client.get(f"/jobs/{job_id}/artifacts", headers=HEADERS)
    assert manifest.status_code == 200, manifest.text
    item = manifest.json()["artifacts"][0]
    assert item["name"] == "result.bin"
    assert item["size"] == 10
    assert item["sha256"] == hashlib.sha256(b"0123456789").hexdigest()

    head = client.head(f"/jobs/{job_id}/artifact/result.bin", headers=HEADERS)
    assert head.status_code == 200
    assert head.headers["accept-ranges"] == "bytes"
    assert head.headers["content-length"] == "10"
    assert head.headers["x-vf-sha256"] == item["sha256"]

    partial = client.get(
        f"/jobs/{job_id}/artifact/result.bin",
        headers={**HEADERS, "Range": "bytes=2-5"},
    )
    assert partial.status_code == 206
    assert partial.content == b"2345"
    assert partial.headers["content-range"] == "bytes 2-5/10"

    invalid = client.get(
        f"/jobs/{job_id}/artifact/result.bin",
        headers={**HEADERS, "Range": "bytes=99-100"},
    )
    assert invalid.status_code == 416


def test_shared_output_failure_keeps_local_artifact(
    client: TestClient, app, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = settings.shared_root / "renders"  # type: ignore[operator]
    output_dir.mkdir(parents=True)
    _register_handler(app, b"local-artifact")

    def broken(*args, **kwargs):
        raise OSError("WinError 32: file is in use")

    monkeypatch.setattr(worker_module, "resolve_shared_output", broken)
    response = client.post(
        "/jobs/fake",
        json={"shared": True, "shared_outputs": ["renders/result.bin"]},
        headers=HEADERS,
    )
    job = _wait(client, response.json()["job_id"])
    assert job["status"] == "succeeded", job
    assert job["artifacts"] == ["result.bin"]
    assert job["shared_artifacts"] == []
    assert "WinError 32" in (job["shared_error"] or "")


class _UploadWorker:
    def __init__(self) -> None:
        self.content = b""
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.startswith("/artifacts/") and request.method == "HEAD":
            return httpx.Response(404, json={"error": "not found"})
        if path == "/artifacts/init":
            return httpx.Response(
                200,
                json={"upload_id": "upload-1", "offset": 0, "chunk_size": 4, "size": 10},
            )
        if path == "/artifacts/upload-1" and request.method == "PATCH":
            self.content += request.content
            return httpx.Response(200, json={"received": len(self.content), "size": 10})
        if path == "/artifacts/upload-1/complete":
            digest = hashlib.sha256(self.content).hexdigest()
            return httpx.Response(200, json={"artifact_id": digest, "bytes": len(self.content)})
        return httpx.Response(404, json={"error": "not found"})


def test_client_uploads_with_resumable_chunks(tmp_path: Path) -> None:
    worker = _UploadWorker()
    http = httpx.Client(transport=httpx.MockTransport(worker))
    client = GPUWorkerClient("http://worker.test", token="secret", http_client=http)
    source = tmp_path / "source.bin"
    source.write_bytes(b"0123456789")

    artifact_id = client.upload_artifact(source)

    assert artifact_id == hashlib.sha256(b"0123456789").hexdigest()
    assert worker.content == b"0123456789"
    methods = [request.method for request in worker.requests]
    assert methods == ["HEAD", "POST", "PATCH", "PATCH", "PATCH", "POST"]


class _DownloadWorker:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        range_header = request.headers.get("range", "")
        if range_header:
            start = int(range_header.split("=")[1].split("-")[0])
            body = self.content[start:]
            return httpx.Response(
                206,
                content=body,
                headers={
                    "Content-Range": f"bytes {start}-{len(self.content) - 1}/{len(self.content)}",
                    "X-VF-Sha256": hashlib.sha256(self.content).hexdigest(),
                },
            )
        return httpx.Response(
            200,
            content=self.content,
            headers={"X-VF-Sha256": hashlib.sha256(self.content).hexdigest()},
        )


def test_client_streams_download_and_resumes(tmp_path: Path) -> None:
    content = b"streamed-artifact"
    worker = _DownloadWorker(content)
    http = httpx.Client(transport=httpx.MockTransport(worker))
    client = GPUWorkerClient("http://worker.test", token="secret", http_client=http)
    target = tmp_path / "out" / "artifact.bin"
    target.parent.mkdir()
    partial = target.parent / f".{target.name}.part"
    partial.write_bytes(content[:4])

    client.download(
        "job-1",
        "artifact.bin",
        target,
        expected_sha256=hashlib.sha256(content).hexdigest(),
    )

    assert target.read_bytes() == content
    assert not partial.exists()
    assert worker.requests[-1].headers["range"] == "bytes=4-"


class _RouterWorker:
    def __init__(self, *, shared: bool = False) -> None:
        self.shared = shared
        self.downloaded: list[str] = []

    def health(self, timeout: float | None = None) -> WorkerHealth:
        return WorkerHealth(
            available=True,
            worker_id="worker-1",
            vram_free_mb=8192,
            capabilities=["fake"],
        )

    def submit(self, capability: str, **kwargs: object) -> str:
        return "job-1"

    def wait(self, job_id: str, timeout: float = 300.0, poll: float = 0.5) -> JobStatus:
        return JobStatus(
            job_id=job_id,
            state="succeeded",
            artifacts=["result.bin"],
            shared_artifacts=["renders/result.bin"] if self.shared else [],
            shared_error="" if self.shared else "WinError 32: file is in use",
        )

    def artifact_manifest(self, job_id: str) -> list[dict[str, object]]:
        return [{"name": "result.bin", "size": 5, "sha256": "a" * 64}]

    def download_all(self, job_id, names, target_dir, *, manifest=None):
        target = Path(target_dir) / "result.bin"
        target.write_bytes(b"http-result")
        self.downloaded.append(str(target))
        return [target]


class _PreparedClient:
    def __init__(self) -> None:
        self.uploaded: list[Path] = []
        self.submitted: dict[str, object] = {}

    def health(self, timeout: float | None = None) -> WorkerHealth:
        return WorkerHealth(
            available=True,
            worker_id="worker-1",
            vram_free_mb=8192,
            capabilities=["fake"],
        )

    def upload_artifact(self, path: str | Path) -> str:
        self.uploaded.append(Path(path))
        return "artifact-1"

    def submit(self, capability: str, **kwargs: object) -> str:
        self.submitted = {"capability": capability, **kwargs}
        return "job-1"

    def wait(self, job_id: str, timeout: float = 300.0, poll: float = 0.5) -> JobStatus:
        return JobStatus(job_id=job_id, state="succeeded", artifacts=["result.bin"])

    def download(self, job_id: str, name: str, target: str | Path) -> Path:
        path = Path(target)
        path.write_bytes(b"ok")
        return path


def test_router_uploads_local_params_and_uses_placeholders(tmp_path: Path) -> None:
    source = tmp_path / "voice.wav"
    source.write_bytes(b"voice")
    worker = _PreparedClient()
    router = ComputeRouter(client=worker, min_vram_mb=0)

    result = router.submit("fake", {"params": {"input": str(source)}})

    assert result["job_id"] == "job-1"
    assert worker.uploaded == [source]
    assert worker.submitted["inputs"] == ["artifact-1"]
    assert worker.submitted["params"] == {"input": "__VF_INPUT_0__"}


def test_router_falls_back_to_http_when_shared_is_empty(tmp_path: Path) -> None:
    shared_root = tmp_path / "shared"
    (shared_root / "renders").mkdir(parents=True)
    (shared_root / "renders" / "result.bin").write_bytes(b"")
    worker = _RouterWorker(shared=True)
    router = ComputeRouter(client=worker, min_vram_mb=0)

    result = router.submit(
        "fake",
        {
            "shared_root": str(shared_root),
            "shared_outputs": ["renders/result.bin"],
        },
    )

    assert result["transport"] == "http_fallback"
    assert result["degraded"] is True
    assert result["degraded_reason"]
    assert result["execution"]["capability"] == "fake"
    assert result["execution"]["degraded"] is True
    assert Path(result["path"]).read_bytes() == b"http-result"
    assert worker.downloaded


def test_router_uses_shared_mount_when_file_is_valid(tmp_path: Path) -> None:
    shared_root = tmp_path / "shared"
    (shared_root / "renders").mkdir(parents=True)
    shared = shared_root / "renders" / "result.bin"
    shared.write_bytes(b"shared-result")
    worker = _RouterWorker(shared=True)
    router = ComputeRouter(client=worker, min_vram_mb=0)

    result = router.submit(
        "fake",
        {
            "shared_root": str(shared_root),
            "shared_outputs": ["renders/result.bin"],
        },
    )

    assert result["transport"] == "shared_mount"
    assert result["degraded"] is False
    assert Path(result["path"]).read_bytes() == b"shared-result"
