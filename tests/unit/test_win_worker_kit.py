from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from videoflow.application import win_worker_kit
from videoflow.application.win_worker_kit import build_worker_kit, kit_info


def _names(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        return set(archive.namelist())


def test_windows_kit_contains_scripts_env_and_readme(tmp_path: Path) -> None:
    result = build_worker_kit(
        output=tmp_path,
        token="secret-token",
        worker_id="worker-1",
        shared_windows_path=r"Z:\videoflow",
        include_worker_source=False,
    )
    names = _names(result.path)
    assert {
        "worker.env",
        "VideoFlowGPU.ps1",
        "VideoFlowGPU.bat",
        "requirements-windows.txt",
        "checksums.txt",
        "expected_version.txt",
        "LEIA-ME.txt",
    } <= names
    with zipfile.ZipFile(result.path) as archive:
        env = archive.read("worker.env").decode("utf-8")
        ps1 = archive.read("VideoFlowGPU.ps1").decode("utf-8")
        bat = archive.read("VideoFlowGPU.bat").decode("utf-8")
        readme = archive.read("LEIA-ME.txt").decode("utf-8")
    assert "VF_GPU_TOKEN=secret-token" in env
    assert "VF_GPU_WORKER_ID=worker-1" in env
    assert "VF_GPU_DISCOVERY=1" in env
    assert r"VF_GPU_SHARED_ROOT=Z:\videoflow" in env
    for token in (
        "Invoke-MenuAction",
        "install-state.json",
        "--no-index",
        "sitecustomize.py",
        "videoflow-gpu-worker.exe",
        "nvidia-smi.exe",
        "h264_nvenc",
        "Register-ScheduledTask",
        "Supervisor",
        "worker.env.bak",
        "--reinstall",
        "taskkill.exe",
        "Tls12",
        "Read-Host",
        "requirements-windows.txt",
    ):
        assert token in ps1
    assert "VideoFlowGPU.ps1" in bat and "--silent" in bat
    assert "goto run" in bat and "pause" in bat
    assert "ONE FILE" in readme
    assert "Self-healing" in readme
    assert "Do not publish" in readme
    assert "offline" in readme.lower()


def test_windows_kit_includes_ffmpeg_when_provided(tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"MZ-ffmpeg")
    (tmp_path / "ffprobe.exe").write_bytes(b"MZ-ffprobe")
    result = build_worker_kit(
        output=tmp_path / "kit",
        ffmpeg_path=ffmpeg,
        include_worker_source=False,
    )
    names = _names(result.path)
    assert "bin/ffmpeg.exe" in names
    assert "bin/ffprobe.exe" in names


def test_windows_kit_includes_prebuilt_worker_wheel(tmp_path: Path) -> None:
    result = build_worker_kit(output=tmp_path, include_worker_source=False)
    names = _names(result.path)
    assert any(name.startswith("wheels/videoflow_gpu_worker-") for name in names)


def test_windows_kit_includes_offline_worker_dependencies(tmp_path: Path) -> None:
    result = build_worker_kit(output=tmp_path, include_worker_source=False)
    names = _names(result.path)
    assert "wheels/pydantic_core-2.50.1-cp311-cp311-win_amd64.whl" in names
    assert "wheels/fastapi-0.149.0-py3-none-any.whl" in names
    with zipfile.ZipFile(result.path) as archive:
        checksums = archive.read("checksums.txt").decode("utf-8")
    assert "videoflow_gpu_worker-" in checksums
    assert "pydantic_core-" in checksums


def test_windows_kit_includes_worker_source_when_requested(tmp_path: Path) -> None:
    result = build_worker_kit(output=tmp_path, include_worker_source=True)
    names = _names(result.path)
    assert "worker/pyproject.toml" in names
    assert "worker/src/gpu_worker/app.py" in names


def test_kit_info_reads_last_metadata(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(win_worker_kit, "portable_home", lambda: tmp_path)
    result = build_worker_kit(
        output=tmp_path / "kits",
        token="token-1",
        worker_id="w-1",
        include_worker_source=False,
    )
    info = kit_info()
    assert info is not None
    assert info["worker_id"] == "w-1"
    assert info["sha256"] == result.sha256
    assert "token" not in info
    assert info["token_location"] == "worker.env inside the zip"


def test_windows_kit_routes_download_and_info(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(win_worker_kit, "portable_home", lambda: tmp_path)
    app = FastAPI()
    from videoflow.api.routes_gpu_worker import register_gpu_worker_routes

    register_gpu_worker_routes(app)
    client = TestClient(app)
    response = client.post(
        "/api/v1/gpu-worker/package",
        json={"token": "route-token", "worker_id": "route-worker"},
    )
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"PK")
    disposition = response.headers.get("content-disposition", "")
    assert "videoflow-windows-gpu-worker-route-worker.zip" in disposition

    info = client.get("/api/v1/gpu-worker/package/info")
    assert info.status_code == 200
    payload = info.json()
    assert payload["worker_id"] == "route-worker"
    assert "token" not in payload
    assert payload["token_included"] is True
    assert payload["token_location"] == "worker.env inside the zip"


def test_windows_kit_sanitizes_ids_and_rejects_newlines(tmp_path: Path) -> None:
    result = build_worker_kit(
        output=tmp_path,
        worker_id="../../evil name",
        include_worker_source=False,
    )
    assert ".." not in result.path.name
    assert "/" not in result.path.name
    assert result.worker_id == "evil-name"
    with pytest.raises(ValueError, match="single line"):
        build_worker_kit(
            output=tmp_path / "bad",
            token="line1\nline2",
            include_worker_source=False,
        )


def test_export_win_worker_cli(tmp_path: Path, capsys) -> None:
    from videoflow import cli

    code = cli.main(
        [
            "export-win-worker",
            "--output",
            str(tmp_path),
            "--token",
            "cli-token",
            "--worker-id",
            "cli-worker",
            "--show-token",
        ]
    )
    assert code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["worker_id"] == "cli-worker"
    assert output["token"] == "cli-token"
    assert Path(output["path"]).is_file()
