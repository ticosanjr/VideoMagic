from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from vf_shared.contracts.locking import FileLock

from videoflow.adapters.ffmpeg.helpers import escape_ffmpeg_filter_path


def test_windows_filter_paths_are_escaped() -> None:
    assert (
        escape_ffmpeg_filter_path(r"C:\Users\Rafael\Edição Vídeo\legenda.ass")
        == "C\\:/Users/Rafael/Edição Vídeo/legenda.ass"
    )
    assert (
        escape_ffmpeg_filter_path(r"C:\Users\O'Brien\sub.ass")
        == "C\\:/Users/O\\'Brien/sub.ass"
    )
    assert (
        escape_ffmpeg_filter_path("C:/Users/Rafael/video/sub.ass")
        == "C\\:/Users/Rafael/video/sub.ass"
    )


def test_posix_filter_path_stays_absolute(tmp_path: Path) -> None:
    target = tmp_path / "legenda.ass"
    escaped = escape_ffmpeg_filter_path(target)
    assert escaped == str(target).replace(":", "\\:")
    assert escaped.startswith("/")


def test_windows_font_dir_uses_windir(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application import fonts

    windir = tmp_path / "Windows"
    target = windir / "Fonts"
    target.mkdir(parents=True)
    monkeypatch.setenv("WINDIR", str(windir))
    assert target in fonts.system_font_dirs()


def test_file_lock_is_exclusive_and_releasable(tmp_path: Path) -> None:
    path = tmp_path / "state.lock"
    first = FileLock(path, blocking=False)
    second = FileLock(path, blocking=False)
    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()
    assert second.acquire() is True
    second.release()


def test_peak_rss_is_optional_without_resource(monkeypatch) -> None:
    from videoflow.application import process_control

    monkeypatch.setattr(process_control, "resource", None)
    assert process_control.peak_rss_mb() is None


def test_core_modules_import_without_posix_only_modules(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    code = """
import builtins

# Preload third-party modules that legitimately choose fcntl/mcp on POSIX.
import mcp.server.stdio  # noqa: F401

_real_import = builtins.__import__


def _import(name, *args, **kwargs):
    if name in {"fcntl", "resource"}:
        raise ImportError(f"{name} is not available")
    return _real_import(name, *args, **kwargs)


builtins.__import__ = _import
import videoflow.api.app
import videoflow.application.projects
import videoflow.mcp_server.agent_tools
print("ok")
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(root / "src"), str(root / "packages" / "vf-shared" / "src")]
    )
    env["VIDEOWFLOW_HOME"] = str(tmp_path)
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "ok" in completed.stdout


def test_render_gate_reports_cross_process_lock(tmp_path: Path) -> None:
    from videoflow.application import render_gate

    gate = render_gate.RenderGate(path=tmp_path / "render.lock")
    with gate.hold("render"):
        assert gate.status()["cross_process"] is True
    status = gate.status()
    assert status["cross_process"] is True
    assert status["active"] is False


def test_windows_stop_uses_taskkill_without_proc(monkeypatch) -> None:
    from types import SimpleNamespace

    from videoflow.application import services

    calls: list[tuple[int, bool]] = []
    monkeypatch.setattr(
        services, "os", SimpleNamespace(name="nt", getpid=lambda: 999_999)
    )
    monkeypatch.setattr(services, "_windows_image_name", lambda _pid: "videoflow.exe")
    monkeypatch.setattr(
        services,
        "terminate_pid",
        lambda pid, *, force=False, timeout=0: calls.append((pid, force)) or True,
    )

    def no_proc(*_args, **_kwargs):
        raise AssertionError("/proc must not be read on Windows")

    monkeypatch.setattr(services, "_ancestors", no_proc)

    assert services.stop_service_pid(4242) is True
    assert calls == [(4242, False)]


def test_windows_discovery_includes_the_pid_file(monkeypatch) -> None:
    from videoflow.application import services

    monkeypatch.setattr(
        services, "read_pid_file", lambda: {"pid": 4321, "port": 8765}
    )
    monkeypatch.setattr(services, "process_alive", lambda pid: pid == 4321)
    monkeypatch.setattr(services, "_windows_listeners", lambda: {})
    monkeypatch.setattr(
        services, "_windows_image_name", lambda _pid: "videoflow.exe"
    )
    monkeypatch.setattr(
        services, "probe_service", lambda *_args, **_kwargs: {"version": "4.3.1"}
    )
    found = services._discover_windows_services(current_pid=1)
    assert [item.pid for item in found] == [4321]
    assert found[0].version == "4.3.1"
    assert found[0].ports == (8765,)


def test_router_accepts_local_gpu_mode(monkeypatch) -> None:
    from vf_shared.compute import COMPUTE_MODES, ComputeRouter

    assert "local_gpu" in COMPUTE_MODES
    monkeypatch.setattr(
        ComputeRouter, "local_gpu_available", property(lambda _self: True)
    )
    router = ComputeRouter(mode="local_gpu")
    assert router.mode == "local_gpu"
    assert router.execution_node == "local_cuda"
    assert router.decide("asr").is_remote is False


def test_asr_local_gpu_policy_selects_cuda_fp16(monkeypatch) -> None:
    from types import SimpleNamespace

    from videoflow.application.settings import AppSettings
    from videoflow.domains.asr import profiles as asr_profiles

    def options(**overrides):
        defaults = {
            "quality_profile": "balanced",
            "mode": "auto",
            "model_id": "",
            "device": "cpu",
            "compute_type": "int8",
            "beam_size": 0,
            "cpu_threads": 0,
            "word_timestamps": "auto",
            "vad_filter": None,
            "condition_on_previous_text": None,
            "base_url": None,
            "model": "whisper-1",
            "api_key_env": "VIDEOWFLOW_ASR_API_KEY",
            "compute_policy": "local_gpu",
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    monkeypatch.delenv("VIDEOWFLOW_ASR_DEVICE", raising=False)
    monkeypatch.delenv("VIDEOWFLOW_ASR_COMPUTE_TYPE", raising=False)
    settings = AppSettings()
    installed = {"faster-whisper-large-v3-turbo": True}

    monkeypatch.setattr(asr_profiles, "_local_gpu_available", lambda: True)
    plan = asr_profiles.resolve_asr_plan(settings, options(), installed=installed)
    assert plan.device == "cuda"
    assert plan.compute_type == "float16"

    monkeypatch.setattr(asr_profiles, "_local_gpu_available", lambda: False)
    fallback = asr_profiles.resolve_asr_plan(settings, options(), installed=installed)
    assert fallback.device == "cpu"
    assert fallback.compute_type == "int8"
    assert "local_gpu" in fallback.fallback_reason


def test_nvenc_local_gpu_requires_cuda_and_probe(monkeypatch) -> None:
    from videoflow.core import nvenc

    monkeypatch.setattr(
        "vf_shared.compute.local_gpu.cuda_device_count", lambda: 0
    )
    assert nvenc.local_gpu_available() is False

    monkeypatch.setattr(
        "vf_shared.compute.local_gpu.cuda_device_count", lambda: 1
    )
    monkeypatch.setattr(
        nvenc, "probe_nvenc", lambda *_args, **_kwargs: nvenc.NvencProbe(True, "", "")
    )
    assert nvenc.local_gpu_available() is True
