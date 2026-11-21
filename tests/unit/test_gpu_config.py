from __future__ import annotations

from pathlib import Path

from vf_shared.compute.config import (
    clear_gpu_config,
    config_path,
    load_gpu_config,
    save_gpu_config,
)
from vf_shared.compute.router import ComputeRouter


def _clear_env(monkeypatch) -> None:
    for name in (
        "VF_COMPUTE_MODE",
        "VF_GPU_WORKER_URL",
        "VF_GPU_WORKER_TOKEN",
        "VF_GPU_WORKER_ID",
        "VF_GPU_TRANSPORT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_gpu_config_roundtrip_and_router_from_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    _clear_env(monkeypatch)
    path = save_gpu_config(
        mode="remote_preferred",
        worker_url="http://192.168.0.42:8766/",
        token="secret-token",
        worker_id="vf-gpu-1",
        transport="http",
    )
    assert path == config_path()
    assert path.is_file()

    config = load_gpu_config()
    assert config.mode == "remote_preferred"
    assert config.worker_url == "http://192.168.0.42:8766"
    assert config.token == "secret-token"
    assert config.worker_id == "vf-gpu-1"
    assert config.transport == "http"
    assert config.source == str(path)

    router = ComputeRouter.from_env()
    assert router.worker_url == "http://192.168.0.42:8766"
    assert router.token == "secret-token"
    assert router.mode == "remote_preferred"
    assert router.transport == "http"


def test_gpu_config_env_overrides_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    _clear_env(monkeypatch)
    save_gpu_config(
        mode="auto",
        worker_url="http://file-worker:8766",
        token="file-token",
        transport="auto",
    )
    monkeypatch.setenv("VF_GPU_WORKER_URL", "http://env-worker:9000")
    monkeypatch.setenv("VF_GPU_WORKER_TOKEN", "env-token")
    monkeypatch.setenv("VF_COMPUTE_MODE", "local_only")

    config = load_gpu_config()
    assert config.worker_url == "http://env-worker:9000"
    assert config.token == "env-token"
    assert config.mode == "local_only"
    assert config.source == "env"


def test_gpu_config_clear(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    _clear_env(monkeypatch)
    save_gpu_config(worker_url="http://worker:8766", token="token")
    clear_gpu_config()
    assert not config_path().exists()
    config = load_gpu_config()
    assert config.worker_url == ""
    assert config.source == "default"
