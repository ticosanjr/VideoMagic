"""Tests for the isolated vf-contracts and vf-compute packages."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_PACKAGES = Path(__file__).resolve().parents[2] / "packages"
for _package in ("vf-contracts", "vf-compute"):
    _src = _PACKAGES / _package / "src"
    if str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

import httpx  # noqa: E402
import pytest  # noqa: E402
from vf_compute.client import GPUWorkerClient, GPUWorkerError  # noqa: E402
from vf_compute.models import JobStatus, WorkerHealth  # noqa: E402
from vf_compute.router import ComputeRouter  # noqa: E402
from vf_contracts.assets import (  # noqa: E402
    asset_key,
    find_cached,
    iter_assets,
    read_sidecar,
    sha256_file,
    sidecar_path,
    write_asset,
)
from vf_contracts.workspace import (  # noqa: E402
    ASSET_KINDS,
    RENDER_VARIANTS,
    asset_dir,
    captions_dir,
    ensure_project,
    project_dir,
    project_state_path,
    read_project,
    render_dir,
    resolve_within,
    workspace_root,
    write_project,
)


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "workspace"
    monkeypatch.setenv("VF_WORKSPACE_ROOT", str(root))
    return root


# ---------------------------------------------------------------------------
# vf-contracts: workspace
# ---------------------------------------------------------------------------


def test_workspace_root_env_and_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VF_WORKSPACE_ROOT", str(tmp_path / "custom"))
    assert workspace_root() == tmp_path / "custom"

    monkeypatch.delenv("VF_WORKSPACE_ROOT")
    monkeypatch.delenv("VIDEOWFLOW_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert workspace_root() == tmp_path / "home" / ".videoflow" / "workspace"


def test_ensure_project_layout_and_metadata(workspace: Path) -> None:
    project = ensure_project("proj-1", name="Demo", output="1080p", channel_id="chan")

    root = project_dir("proj-1")
    assert root == workspace / "projects" / "proj-1"
    assert (root / "script").is_dir()
    assert (root / "captions").is_dir()
    for kind in ASSET_KINDS:
        assert (root / "assets" / kind).is_dir()
    for variant in RENDER_VARIANTS:
        assert (root / "renders" / variant).is_dir()

    assert project["workspace_version"] == 1
    assert project["project_id"] == "proj-1"
    assert project["name"] == "Demo"
    assert project["channel_id"] == "chan"
    assert project["output"] == "1080p"
    assert project["sources"] == []
    assert project["state_path"] == str(root / "state.json")
    assert project["created_at"]
    assert project["updated_at"]

    on_disk = json.loads((root / "project.json").read_text(encoding="utf-8"))
    assert on_disk == project
    assert read_project("proj-1") == project

    assert project_state_path("proj-1") == root / "state.json"
    assert asset_dir("proj-1", "voice") == root / "assets" / "voice"
    assert captions_dir("proj-1") == root / "captions"
    assert render_dir("proj-1", "final") == root / "renders" / "final"


def test_ensure_project_preserves_existing_metadata(workspace: Path) -> None:
    first = ensure_project("proj-2", name="Keep", output="720p", channel_id="c")
    second = ensure_project("proj-2")

    assert second["name"] == "Keep"
    assert second["output"] == "720p"
    assert second["channel_id"] == "c"
    assert second["created_at"] == first["created_at"]

    third = ensure_project("proj-2", name="New")
    assert third["name"] == "New"
    assert third["output"] == "720p"


def test_write_project_roundtrip(workspace: Path) -> None:
    original = ensure_project("proj-3", name="Before", output="4k")
    updated = dict(original)
    updated["name"] = "After"
    written = write_project("proj-3", updated)

    assert written["name"] == "After"
    assert written["project_id"] == "proj-3"
    assert written["created_at"] == original["created_at"]
    assert read_project("proj-3")["name"] == "After"

    partial = write_project("proj-3", {"name": "Partial"})
    assert partial["name"] == "Partial"
    assert partial["output"] == "4k"
    assert partial["created_at"] == original["created_at"]


@pytest.mark.parametrize("project_id", ["../escape", "a/b", ".", "..", "", "bad id"])
def test_project_dir_rejects_unsafe_ids(workspace: Path, project_id: str) -> None:
    with pytest.raises(ValueError):
        project_dir(project_id)


@pytest.mark.parametrize(
    "relative_path",
    ["../escape", "/etc/passwd", "assets/../../outside", "a/b/../../../c"],
)
def test_resolve_within_rejects_traversal(
    workspace: Path, relative_path: str
) -> None:
    ensure_project("proj-4")
    with pytest.raises(ValueError):
        resolve_within("proj-4", relative_path)


def test_resolve_within_accepts_project_paths(workspace: Path) -> None:
    ensure_project("proj-5")
    root = project_dir("proj-5").resolve()
    resolved = resolve_within("proj-5", "assets/voice/clip.wav")
    assert resolved == root / "assets" / "voice" / "clip.wav"
    assert resolve_within("proj-5", ".") == root


# ---------------------------------------------------------------------------
# vf-contracts: assets
# ---------------------------------------------------------------------------


def test_asset_key_is_deterministic() -> None:
    first = asset_key(
        "tts",
        {"voice": "alloy", "nested": {"speed": 1.0, "seed": 7}},
        model="tts-1",
        version="v2",
    )
    second = asset_key(
        "tts",
        {"nested": {"seed": 7, "speed": 1.0}, "voice": "alloy"},
        model="tts-1",
        version="v2",
    )
    assert first == second
    assert len(first) == 64
    assert asset_key("tts", {"voice": "alloy"}) != first
    assert asset_key("tts", {"voice": "nova"}, model="tts-1", version="v2") != first


def test_sha256_file_streams_content(tmp_path: Path) -> None:
    path = tmp_path / "blob.bin"
    path.write_bytes(b"abc" * 100_000)
    assert sha256_file(path) == hashlib.sha256(b"abc" * 100_000).hexdigest()
    assert sha256_file(path, chunk_size=7) == sha256_file(path)


def test_write_asset_is_idempotent_and_indexed(workspace: Path) -> None:
    ensure_project("proj-6")
    key = asset_key(
        "tts",
        {"voice": "alloy", "text": "hello"},
        model="tts-1",
        version="1",
    )
    fields = {
        "source": "ai",
        "provider": "openai",
        "model": "tts-1",
        "model_version": "1",
        "license": "ai_generated",
        "attribution_required": False,
        "duration_sec": 1.25,
        "sample_rate": 48_000,
        "channels": 1,
        "codec": "wav",
        "params_hash": key,
    }

    record = write_asset("proj-6", "voice", b"voice-bytes", fields)
    root = project_dir("proj-6")
    destination = root / record.path
    assert destination.read_bytes() == b"voice-bytes"
    assert record.sha256 == hashlib.sha256(b"voice-bytes").hexdigest()
    assert record.bytes == len(b"voice-bytes")
    assert record.path == f"assets/voice/{record.sha256}.bin"
    assert record.project_id == "proj-6"
    assert record.params_hash == key

    meta = sidecar_path(destination)
    assert meta.is_file()
    assert read_sidecar(destination) == record
    assert read_sidecar(meta) == record

    again = write_asset("proj-6", "voice", b"voice-bytes", fields)
    assert again.asset_id == record.asset_id
    assert again.created_at == record.created_at
    assert again.path == record.path

    assets = list(iter_assets("proj-6"))
    assert [item.asset_id for item in assets] == [record.asset_id]
    assert list(iter_assets("proj-6", "voice")) == assets
    assert list(iter_assets("proj-6", "music")) == []

    index = json.loads((root / "assets" / "index.json").read_text(encoding="utf-8"))
    assert index["version"] == 1
    assert [entry["asset_id"] for entry in index["assets"]] == [record.asset_id]

    assert find_cached("proj-6", "voice", key) == record
    assert find_cached("proj-6", "voice", record.asset_id) == record
    assert find_cached("proj-6", "voice", "no-such-key") is None
    assert find_cached("proj-6", "music", key) is None


def test_write_asset_copies_files_and_preserves_extension(
    workspace: Path, tmp_path: Path
) -> None:
    ensure_project("proj-7")
    source = tmp_path / "track.MP3"
    source.write_bytes(b"music-bytes")
    key = asset_key("music_search", {"query": "calm"})

    record = write_asset(
        "proj-7",
        "music",
        source,
        {"source": "pixabay", "license": "pixabay", "params_hash": key},
    )

    assert record.path.endswith(f"{record.sha256}.mp3")
    assert record.bytes == len(b"music-bytes")
    assert record.sha256 == sha256_file(source)
    assert str(tmp_path) not in record.path
    assert (project_dir("proj-7") / record.path).read_bytes() == b"music-bytes"
    assert source.read_bytes() == b"music-bytes"
    assert find_cached("proj-7", "music", key) == record


def test_write_asset_rejects_unsafe_inputs(
    workspace: Path, tmp_path: Path
) -> None:
    ensure_project("proj-8")
    with pytest.raises(ValueError):
        write_asset("proj-8", "../voice", b"x")
    with pytest.raises(ValueError):
        write_asset("../escape", "voice", b"x")
    with pytest.raises(FileNotFoundError):
        write_asset("proj-8", "voice", tmp_path / "missing.wav")


# ---------------------------------------------------------------------------
# vf-compute: models
# ---------------------------------------------------------------------------


def test_health_and_job_models_tolerate_payload_variants() -> None:
    health = WorkerHealth.from_payload(
        {
            "status": "ok",
            "gpu": "ada",
            "vram_free": "4096",
            "vram_total": 12_288,
            "capabilities": ("upscale",),
            "models": ["sdxl"],
            "queue": 1,
        }
    )
    assert health.available is True
    assert health.gpu_name == "ada"
    assert health.vram_free_mb == 4096
    assert health.vram_total_mb == 12_288
    assert health.capabilities == ["upscale"]
    assert health.models_loaded == ["sdxl"]
    assert health.models == ["sdxl"]
    assert health.queue_depth == 1

    status = JobStatus.from_payload(
        {"id": "job-x", "status": "DONE", "outputs": ["clip.mp4"]}
    )
    assert status.job_id == "job-x"
    assert status.done is True
    assert status.ok is True
    assert status.artifacts == ["clip.mp4"]

    failed = JobStatus.from_payload({"state": "failed", "error": "boom"}, job_id="j")
    assert failed.done is True
    assert failed.ok is False
    assert failed.error == "boom"


# ---------------------------------------------------------------------------
# vf-compute: fake worker and router
# ---------------------------------------------------------------------------


class FakeWorker:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.health_status = 200
        self.health_payload: dict[str, Any] = {
            "available": True,
            "gpu_name": "fake-gpu",
            "vram_free_mb": 8192,
            "vram_total_mb": 12_288,
            "capabilities": ["upscale", "tts"],
            "models": ["sdxl"],
            "queue_depth": 0,
        }
        self.statuses: list[dict[str, Any]] = [{"state": "succeeded"}]
        self.download_body = b"artifact-bytes"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/health":
            if self.health_status != 200:
                return httpx.Response(self.health_status, json={"error": "down"})
            return httpx.Response(200, json=self.health_payload)
        if path == "/artifacts":
            return httpx.Response(200, json={"artifact_id": "artifact-1"})
        if path.startswith("/jobs/") and request.method == "POST":
            return httpx.Response(200, json={"job_id": "job-1"})
        if path == "/jobs/job-1":
            payload = (
                self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            )
            return httpx.Response(200, json={"job_id": "job-1", **payload})
        if path == "/jobs/job-1/artifact/clip.mp4":
            return httpx.Response(200, content=self.download_body)
        return httpx.Response(404, json={"error": "not found"})

    def health_calls(self) -> list[httpx.Request]:
        return [request for request in self.requests if request.url.path == "/health"]


def _client(worker: FakeWorker) -> GPUWorkerClient:
    http = httpx.Client(transport=httpx.MockTransport(worker))
    return GPUWorkerClient("http://worker.test", token="secret", http_client=http)


def _router(
    worker: FakeWorker,
    monkeypatch: pytest.MonkeyPatch,
    **env: str,
) -> ComputeRouter:
    values = {
        "VF_COMPUTE_MODE": "auto",
        "VF_GPU_WORKER_URL": "http://worker.test",
        "VF_GPU_WORKER_TOKEN": "secret",
        "VF_GPU_HEALTH_TTL_SEC": "5",
        "VF_GPU_HEALTH_TIMEOUT_SEC": "0.3",
        "VF_GPU_MIN_VRAM_MB": "2048",
        "VF_GPU_MAX_QUEUE": "2",
        "VF_GPU_CIRCUIT_SEC": "30",
    }
    values.update(env)
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return ComputeRouter.from_env(client=_client(worker))


def test_router_health_cache_and_force(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = FakeWorker()
    router = _router(worker, monkeypatch)

    first = router.decide("upscale", required_vram_mb=1024)
    second = router.decide("upscale", required_vram_mb=1024)
    assert first.mode == "remote"
    assert second.mode == "remote"
    assert len(worker.health_calls()) == 1

    router.health(force=True)
    assert len(worker.health_calls()) == 2

    router.health_ttl = 0.0
    router.health()
    assert len(worker.health_calls()) == 3


def test_router_circuit_breaker(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = FakeWorker()
    worker.health_status = 503
    router = _router(worker, monkeypatch)
    router.health_ttl = 0.0

    first = router.health()
    assert first.available is False
    assert len(worker.health_calls()) == 1

    cached = router.health()
    assert cached.available is False
    assert len(worker.health_calls()) == 1

    forced = router.health(force=True)
    assert forced.available is False
    assert len(worker.health_calls()) == 2

    worker.health_status = 200
    recovered = router.health(force=True)
    assert recovered.available is True
    assert recovered.gpu_name == "fake-gpu"


def test_router_auto_remote_and_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = FakeWorker()
    router = _router(worker, monkeypatch)

    assert router.decide("upscale", required_vram_mb=8192).mode == "remote"

    missing = router.decide("musicgen")
    assert missing.mode == "local"
    assert "capability" in missing.reason

    low_vram = router.decide("upscale", required_vram_mb=8193)
    assert low_vram.mode == "local"
    assert "vram" in low_vram.reason

    worker.health_payload["queue_depth"] = 2
    router.health(force=True)
    busy = router.decide("upscale")
    assert busy.mode == "local"
    assert "queue" in busy.reason

    worker.health_status = 503
    router.health(force=True)
    down = router.decide("upscale")
    assert down.mode == "local"
    assert "unavailable" in down.reason


def test_router_local_only_never_calls_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = FakeWorker()
    router = _router(worker, monkeypatch, VF_COMPUTE_MODE="local_only")

    decision = router.decide("upscale", required_vram_mb=1)
    assert decision.mode == "local"
    assert "local_only" in decision.reason
    assert worker.health_calls() == []
    assert worker.requests == []

    health = router.health(force=True)
    assert health.available is False
    assert worker.requests == []


def test_router_remote_preferred_falls_back_with_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = FakeWorker()
    router = _router(worker, monkeypatch, VF_COMPUTE_MODE="remote_preferred")
    assert router.decide("tts").mode == "remote"

    worker.health_status = 500
    router.health(force=True)
    fallback = router.decide("tts", required_vram_mb=512)
    assert fallback.mode == "local"
    assert fallback.capability == "tts"
    assert fallback.reason


def test_router_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        ComputeRouter(mode="turbo")


# ---------------------------------------------------------------------------
# vf-compute: client
# ---------------------------------------------------------------------------


def test_client_health_and_upload(
    tmp_path: Path,
) -> None:
    worker = FakeWorker()
    client = _client(worker)

    health = client.health()
    assert health.available is True
    assert health.models_loaded == ["sdxl"]
    assert worker.requests[0].headers["X-VF-Token"] == "secret"

    assert client.upload_artifact(b"raw-bytes") == "artifact-1"
    upload = worker.requests[-1]
    assert upload.method == "POST"
    assert upload.url.path == "/artifacts"
    assert b"raw-bytes" in upload.content

    source = tmp_path / "voice.wav"
    source.write_bytes(b"wav-bytes")
    assert client.upload_artifact(source) == "artifact-1"
    assert b"voice.wav" in worker.requests[-1].content


def test_client_streams_file_uploads_without_read_bytes(
    tmp_path: Path, monkeypatch
) -> None:
    worker = FakeWorker()
    client = _client(worker)
    source = tmp_path / "voice.wav"
    source.write_bytes(b"wav-bytes")

    def forbidden(self):
        raise AssertionError("upload_artifact must not call Path.read_bytes")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    assert client.upload_artifact(source) == "artifact-1"
    assert b"wav-bytes" in worker.requests[-1].content


def test_client_submit_shared_and_status_wait() -> None:
    worker = FakeWorker()
    worker.statuses = [
        {"state": "running", "progress": 0.5},
        {"state": "succeeded", "outputs": ["clip.mp4"]},
    ]
    client = _client(worker)

    job_id = client.submit(
        "upscale",
        {"scale": 2},
        ["artifact-1"],
        shared_root="/mnt/workspace",
        shared_inputs=["projects/p1/assets/images/a.png"],
    )
    assert job_id == "job-1"
    submit_request = worker.requests[-1]
    assert submit_request.url.path == "/jobs/upscale"
    body = json.loads(submit_request.content)
    assert body["params"] == {"scale": 2}
    assert body["inputs"] == ["artifact-1"]
    assert body["shared"] is True
    assert body["input_paths"] == ["projects/p1/assets/images/a.png"]
    assert body["shared_inputs"] == ["projects/p1/assets/images/a.png"]

    plain_id = client.submit("tts", {"voice": "alloy"})
    assert plain_id == "job-1"
    plain_request = worker.requests[-1]
    assert plain_request.url.path == "/jobs/tts"
    plain = json.loads(plain_request.content)
    assert plain["shared"] is False
    assert "input_paths" not in plain
    assert "shared_inputs" not in plain

    status = client.wait("job-1", timeout=2.0, poll=0.0)
    assert status.job_id == "job-1"
    assert status.state == "succeeded"
    assert status.done is True
    assert status.ok is True
    assert status.artifacts == ["clip.mp4"]


def test_client_download_and_path_validation(tmp_path: Path) -> None:
    worker = FakeWorker()
    client = _client(worker)

    target = tmp_path / "downloads" / "clip.mp4"
    result = client.download("job-1", "clip.mp4", target)
    assert result == target
    assert target.read_bytes() == b"artifact-bytes"
    assert worker.requests[-1].url.path == "/jobs/job-1/artifact/clip.mp4"

    calls = len(worker.requests)
    with pytest.raises(ValueError):
        client.download("job-1", "../secret.mp4", tmp_path / "x.mp4")
    with pytest.raises(ValueError):
        client.download("../job-1", "clip.mp4", tmp_path / "x.mp4")
    assert len(worker.requests) == calls


def test_client_wraps_http_failures() -> None:
    worker = FakeWorker()
    client = _client(worker)

    with pytest.raises(GPUWorkerError):
        client.status("missing-job")

    with pytest.raises(ValueError):
        GPUWorkerClient("")
