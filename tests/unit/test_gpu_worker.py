"""Unit tests for the isolated GPU worker package."""

from __future__ import annotations

import sys
import time
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[2] / "packages" / "gpu-worker" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from gpu_worker.app import create_app  # noqa: E402
from gpu_worker.settings import Settings  # noqa: E402

TOKEN = "test-token"
HEADERS = {"X-VF-Token": TOKEN}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    shared_root = tmp_path / "shared"
    shared_root.mkdir()
    return Settings(
        token=TOKEN,
        work_dir=tmp_path / "worker",
        max_upload_mb=1,
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


def upload(
    client: TestClient,
    content: bytes = b"clip",
    name: str = "clip.wav",
    *,
    headers: dict[str, str] = HEADERS,
) -> dict:
    response = client.post(
        "/artifacts",
        files={"file": (name, content, "application/octet-stream")},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def wait_for_job(
    client: TestClient,
    job_id: str,
    *,
    timeout: float = 5.0,
    headers: dict[str, str] = HEADERS,
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/jobs/{job_id}", headers=headers)
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] in {"succeeded", "failed", "cancelled"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("job did not finish before the timeout")


def register_result_handler(app, content: str = "handled", seen: dict | None = None):
    def handler(params, input_paths, work_dir):
        if seen is not None:
            seen["params"] = params
            seen["inputs"] = [path.read_bytes() for path in input_paths]
        output = work_dir / "result.txt"
        output.write_text(content, encoding="utf-8")
        return [output]

    app.state.registry.register_handler("fake", handler)
    return handler


def test_health_is_public_and_reports_worker_state(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200, response.text
    payload = response.json()
    for key in (
        "available",
        "gpu_name",
        "vram_free_mb",
        "vram_total_mb",
        "vram_used_mb",
        "gpu_utilization",
        "temperature_c",
        "worker_id",
        "hostname",
        "ip_local",
        "port",
        "platform",
        "capabilities",
        "models",
        "queue_depth",
    ):
        assert key in payload
    assert isinstance(payload["available"], bool)
    assert payload["available"] is True
    assert isinstance(payload["gpu_name"], str) and payload["gpu_name"]
    assert isinstance(payload["vram_free_mb"], int)
    assert isinstance(payload["vram_total_mb"], int)
    assert payload["capabilities"] == []
    assert payload["models"] == []
    assert payload["queue_depth"] == 0
    assert "tts" in payload["unavailable_capabilities"]


def test_non_health_requires_the_configured_token(client: TestClient) -> None:
    response = client.post("/artifacts", files={"file": ("a.wav", b"a")})
    assert response.status_code == 401

    response = client.post(
        "/artifacts",
        files={"file": ("a.wav", b"a")},
        headers={"X-VF-Token": "wrong"},
    )
    assert response.status_code == 401

    assert upload(client, b"a")["bytes"] == 1


def test_missing_configured_token_blocks_non_health(tmp_path: Path) -> None:
    application = create_app(Settings(token=None, work_dir=tmp_path / "worker"))
    try:
        with TestClient(application) as test_client:
            assert test_client.get("/health").status_code == 200
            response = test_client.post("/artifacts", files={"file": ("a.wav", b"a")})
            assert response.status_code == 503
            assert "VF_GPU_TOKEN" in response.json()["detail"]
    finally:
        application.state.close()


def test_upload_is_content_addressed(client: TestClient) -> None:
    first = upload(client, b"same-bytes", "first.wav")
    second = upload(client, b"same-bytes", "second.wav")
    different = upload(client, b"other-bytes", "third.wav")

    assert first["artifact_id"] == second["artifact_id"]
    assert first["sha256"] == first["artifact_id"]
    assert len(first["artifact_id"]) == 64
    assert first["bytes"] == len(b"same-bytes")
    assert different["artifact_id"] != first["artifact_id"]


def test_upload_rejects_files_over_the_limit(client: TestClient) -> None:
    response = client.post(
        "/artifacts",
        files={"file": ("big.bin", b"x" * (1024 * 1024 + 1))},
        headers=HEADERS,
    )
    assert response.status_code == 413


def test_env_settings_and_builtin_command_handler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "fake_tts.py"
    script.write_text(
        "import sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_bytes(b'tts-bytes')\n",
        encoding="utf-8",
    )
    for name in (
        "VF_GPU_HOST",
        "VF_GPU_PORT",
        "VF_GPU_MAX_UPLOAD_MB",
        "VF_GPU_MAX_QUEUE",
        "VF_GPU_MODEL_TTL_SEC",
        "VF_GPU_SHARED_ROOT",
        "VF_ACE_STEP_CMD",
        "VF_STABLE_AUDIO_CMD",
        "VF_AUDIO_SEPARATOR_CMD",
        "VF_REALESRGAN_CMD",
        "VF_GPU_COMFYUI_URL",
        "VF_COMFYUI_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VF_GPU_TOKEN", "env-token")
    monkeypatch.setenv("VF_GPU_WORK_DIR", str(tmp_path / "env-worker"))
    monkeypatch.setenv("VF_CHATTERBOX_CMD", f"{sys.executable} {script}")

    loaded = Settings.from_env()
    assert loaded.token == "env-token"
    assert loaded.work_dir == tmp_path / "env-worker"
    assert loaded.host == "0.0.0.0"
    assert loaded.port == 8766
    assert loaded.chatterbox_cmd == f"{sys.executable} {script}"

    application = create_app()
    try:
        with TestClient(application) as test_client:
            health = test_client.get("/health").json()
            assert health["capabilities"] == ["tts"]
            response = test_client.post(
                "/jobs/tts",
                json={"params": {"text": "hello"}},
                headers={"X-VF-Token": "env-token"},
            )
            assert response.status_code == 200, response.text
            job = wait_for_job(
                test_client, response.json()["job_id"], headers={"X-VF-Token": "env-token"}
            )
            assert job["status"] == "succeeded", job
            download = test_client.get(
                f"/jobs/{job['job_id']}/artifact/tts.wav",
                headers={"X-VF-Token": "env-token"},
            )
            assert download.content == b"tts-bytes"
    finally:
        application.state.close()


def test_fake_handler_job_succeeds_and_downloads_artifact(client: TestClient, app) -> None:
    seen: dict = {}
    register_result_handler(app, "fake-result", seen)
    artifact = upload(client, b"source-audio", "source.wav")

    response = client.post(
        "/jobs/fake",
        json={"params": {"label": "hello"}, "inputs": [artifact["artifact_id"]]},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    submitted = response.json()
    assert submitted["status"] == "queued"
    assert len(submitted["job_id"]) == 32

    job = wait_for_job(client, submitted["job_id"])
    assert job["status"] == "succeeded", job
    assert job["artifacts"] == ["result.txt"]
    assert seen["params"] == {"label": "hello"}
    assert seen["inputs"] == [b"source-audio"]

    download = client.get(f"/jobs/{submitted['job_id']}/artifact/result.txt", headers=HEADERS)
    assert download.status_code == 200
    assert download.content == b"fake-result"


def test_handler_failure_marks_the_job_failed(client: TestClient, app) -> None:
    def handler(params, input_paths, work_dir):
        raise RuntimeError("synthetic boom")

    app.state.registry.register_handler("fake", handler)
    response = client.post("/jobs/fake", json={}, headers=HEADERS)
    assert response.status_code == 200

    job = wait_for_job(client, response.json()["job_id"])
    assert job["status"] == "failed"
    assert "synthetic boom" in job["error"]


def test_shared_inputs_are_passed_to_the_handler(
    client: TestClient, app, settings: Settings
) -> None:
    assert settings.shared_root is not None
    (settings.shared_root / "clip.wav").write_bytes(b"shared-audio")
    seen: dict = {}
    register_result_handler(app, seen=seen)

    response = client.post(
        "/jobs/fake",
        json={"shared": True, "shared_inputs": ["clip.wav"]},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    job = wait_for_job(client, response.json()["job_id"])
    assert job["status"] == "succeeded"
    assert seen["inputs"] == [b"shared-audio"]


def test_shared_input_traversal_is_rejected(client: TestClient, app, settings: Settings) -> None:
    assert settings.shared_root is not None
    (settings.shared_root.parent / "secret.txt").write_text("secret", encoding="utf-8")
    register_result_handler(app)

    for relative in ("../secret.txt", "/etc/passwd", "nested/../../secret.txt"):
        response = client.post(
            "/jobs/fake",
            json={"shared": True, "shared_inputs": [relative]},
            headers=HEADERS,
        )
        assert response.status_code == 400, (relative, response.text)


def test_invalid_artifact_ids_and_capabilities_are_rejected(client: TestClient, app) -> None:
    register_result_handler(app)

    invalid_input = client.post(
        "/jobs/fake", json={"inputs": ["../../etc/passwd"]}, headers=HEADERS
    )
    assert invalid_input.status_code == 400

    unknown = client.post("/jobs/not-a-capability", json={}, headers=HEADERS)
    assert unknown.status_code == 404

    unavailable = client.post("/jobs/tts", json={"params": {}}, headers=HEADERS)
    assert unavailable.status_code == 501
    assert "VF_CHATTERBOX_CMD" in unavailable.json()["detail"]


def test_artifact_download_rejects_traversal(client: TestClient, app) -> None:
    register_result_handler(app)
    response = client.post("/jobs/fake", json={}, headers=HEADERS)
    job = wait_for_job(client, response.json()["job_id"])
    assert job["status"] == "succeeded"

    traversal = client.get(f"/jobs/{job['job_id']}/artifact/..%2Fsecret.txt", headers=HEADERS)
    assert traversal.status_code == 404

    missing = client.get(f"/jobs/{job['job_id']}/artifact/secret.txt", headers=HEADERS)
    assert missing.status_code == 404


def test_job_delete_removes_state(client: TestClient, app) -> None:
    register_result_handler(app)
    response = client.post("/jobs/fake", json={}, headers=HEADERS)
    job = wait_for_job(client, response.json()["job_id"])

    deleted = client.delete(f"/jobs/{job['job_id']}", headers=HEADERS)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(f"/jobs/{job['job_id']}", headers=HEADERS).status_code == 404


def test_model_registry_unloads_idle_models(client: TestClient, app) -> None:
    unloaded: list[str] = []
    models = app.state.models
    models.register(
        "fake-model",
        capability="tts",
        unload=lambda: unloaded.append("fake-model"),
    )
    assert models.snapshot()[0]["name"] == "fake-model"
    assert client.get("/health").json()["models"] == ["fake-model"]

    expired = models.sweep(now=time.time() + app.state.settings.model_ttl_sec + 1.0)
    assert expired == ["fake-model"]
    assert unloaded == ["fake-model"]
    assert models.snapshot() == []


def test_asr_and_diarize_are_allowlisted_handlers(tmp_path: Path) -> None:
    from gpu_worker.handlers import BUILTIN_CAPABILITIES, build_default_registry

    assert "asr" in BUILTIN_CAPABILITIES
    assert "diarize" in BUILTIN_CAPABILITIES
    settings = Settings(
        work_dir=tmp_path / "worker",
        asr_cmd="/bin/true {input} {output}",
        diarize_cmd="/bin/true {input} {output}",
    )
    registry = build_default_registry(settings)
    assert registry.is_available("asr") is True
    assert registry.is_available("diarize") is True
    assert "asr" in registry.available()
    assert "diarize" in registry.available()


def test_asr_and_diarize_report_missing_commands(tmp_path: Path) -> None:
    from gpu_worker.handlers import build_default_registry

    registry = build_default_registry(Settings(work_dir=tmp_path / "worker"))
    assert registry.is_available("asr") is False
    assert "VF_GPU_ASR_CMD" in registry.reason("asr")
    assert "VF_GPU_DIARIZE_CMD" in registry.reason("diarize")


def test_shared_outputs_write_into_the_mount(
    client: TestClient, app, settings: Settings
) -> None:
    output_dir = settings.shared_root / "renders"  # type: ignore[operator]
    output_dir.mkdir(parents=True)
    register_result_handler(app, "shared-result")
    response = client.post(
        "/jobs/fake",
        json={
            "params": {},
            "shared": True,
            "shared_outputs": ["renders/result.txt"],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    job = wait_for_job(client, response.json()["job_id"])
    assert job["status"] == "succeeded", job
    assert job["shared_artifacts"] == ["renders/result.txt"]
    assert (output_dir / "result.txt").read_text(encoding="utf-8") == "shared-result"


def test_shared_outputs_reject_traversal_and_missing_parent(
    client: TestClient, settings: Settings
) -> None:
    for relative in ("../escape.txt", "missing/result.txt", "/tmp/escape.txt"):
        response = client.post(
            "/jobs/fake",
            json={"params": {}, "shared": True, "shared_outputs": [relative]},
            headers=HEADERS,
        )
        assert response.status_code in {400, 404}, response.text


def test_models_unload_and_shared_validation(
    client: TestClient, app, settings: Settings
) -> None:
    app.state.models.register("model-a", vram_mb=1024)
    unloaded = client.post("/models/unload", json={}, headers=HEADERS)
    assert unloaded.status_code == 200, unloaded.text
    assert unloaded.json()["unloaded"] == ["model-a"]
    assert app.state.models.vram_used_mb() == 0

    (settings.shared_root / "renders").mkdir(parents=True, exist_ok=True)  # type: ignore[operator]
    valid = client.post(
        "/shared/validate",
        json={"path": "renders/probe.txt"},
        headers=HEADERS,
    )
    assert valid.status_code == 200, valid.text
    assert not (settings.shared_root / "renders" / "probe.txt").exists()  # type: ignore[operator]

    invalid = client.post(
        "/shared/validate",
        json={"path": "../escape.txt"},
        headers=HEADERS,
    )
    assert invalid.status_code == 400, invalid.text


def test_lan_open_mode_allows_private_clients_without_token(tmp_path: Path) -> None:
    application = create_app(
        Settings(
            token="secret",
            allow_lan_open=True,
            work_dir=tmp_path / "worker",
        )
    )
    try:
        with TestClient(application, client=("192.168.1.50", 50000)) as test_client:
            response = test_client.post(
                "/artifacts", files={"file": ("a.wav", b"a")}
            )
            assert response.status_code == 200, response.text
            health = test_client.get("/health").json()
            assert health["auth_mode"] == "lan_open"
            assert health["encoder"] in {"nvenc", "libx264"}
    finally:
        application.state.close()


def test_lan_open_mode_rejects_public_clients(tmp_path: Path) -> None:
    application = create_app(
        Settings(
            token="secret",
            allow_lan_open=True,
            work_dir=tmp_path / "worker",
        )
    )
    try:
        with TestClient(application, client=("8.8.8.8", 50000)) as test_client:
            response = test_client.post(
                "/artifacts", files={"file": ("a.wav", b"a")}
            )
            assert response.status_code == 401
    finally:
        application.state.close()


def test_worker_dashboard_and_overview(client: TestClient) -> None:
    with TestClient(client.app, client=("127.0.0.1", 50000)) as local:
        page = local.get("/ui/")
        assert page.status_code == 200
        assert "VideoFlow" in page.text
        overview = local.get("/api/overview")
        assert overview.status_code == 200
        payload = overview.json()
        assert payload["ok"] is True
        assert "health" in payload and "jobs" in payload
        assert payload["health"]["auth_mode"] in {"token", "lan_open", "none"}
        assert "encoder" in payload["health"]
        jobs = local.get("/api/jobs?limit=5")
        assert jobs.status_code == 200
        assert isinstance(jobs.json()["jobs"], list)


def test_worker_health_reports_encoder_and_activity(client: TestClient) -> None:
    payload = client.get("/health").json()
    assert payload["uptime_sec"] >= 0
    assert payload["encoder"] in {"nvenc", "libx264"}
    assert isinstance(payload["lan_urls"], list)
    assert "current_job" in payload


def test_warmup_endpoint_requires_builtin_handlers(client: TestClient) -> None:
    response = client.post("/api/warmup", headers=HEADERS)
    assert response.status_code == 409
    assert "VF_GPU_BUILTIN_HANDLERS" in response.json()["detail"]


def test_job_reports_priority_stage_and_progress(client: TestClient, app) -> None:
    from gpu_worker.progress import report

    def handler(params, input_paths, work_dir):
        report("analyzing", 55)
        target = Path(work_dir) / "result.txt"
        target.write_text("ok", encoding="utf-8")
        return [target]

    app.state.registry.register_handler("fake", handler)
    response = client.post(
        "/jobs/fake",
        json={"priority": 7},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    job = wait_for_job(client, response.json()["job_id"])
    assert job["priority"] == 7
    assert job["progress"] == 100
    assert job["stage"] == "succeeded"
    assert job["status"] == "succeeded"


def test_worker_dashboard_assets_are_served(client: TestClient) -> None:
    index = client.get("/ui/", headers=HEADERS)
    assert index.status_code == 200
    assert "/ui/app.js" in index.text
    assert "/ui/app.css" in index.text
    script = client.get("/ui/app.js", headers=HEADERS)
    assert script.status_code == 200
    assert "api/overview" in script.text
    styles = client.get("/ui/app.css", headers=HEADERS)
    assert styles.status_code == 200
    assert "--accent" in styles.text
