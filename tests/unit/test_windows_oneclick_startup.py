"""v4.6 one-click startup: model bootstrap, tray, ports, and restart."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.application import bootstrap_runtime, database, tray


@pytest.fixture(autouse=True)
def _fresh_bootstrap():
    bootstrap_runtime.reset_bootstrap_for_tests()
    yield
    bootstrap_runtime.reset_bootstrap_for_tests()


def test_bootstrap_is_disabled_by_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_NO_AUTO_DOWNLOAD", "1")
    calls: list[str] = []
    monkeypatch.setattr(
        bootstrap_runtime, "install_model", lambda *args, **kwargs: calls.append("x")
    )
    assert bootstrap_runtime.auto_download_disabled() is True
    assert bootstrap_runtime.ensure_essential_models_async() is None
    assert calls == []


def test_bootstrap_installs_missing_models_and_records_jobs(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.delenv("VIDEOWFLOW_NO_AUTO_DOWNLOAD", raising=False)
    monkeypatch.setattr(bootstrap_runtime, "installed_path", lambda model_id: None)
    installed: list[str] = []
    invalidated: list[bool] = []

    def fake_install(model_id, *, allow_network=True, progress=None):
        installed.append(model_id)
        if progress is not None:
            progress(40, f"Downloading {model_id}")
            progress(100, "Installed")
        return {"id": model_id, "installed": True}

    monkeypatch.setattr(bootstrap_runtime, "install_model", fake_install)
    monkeypatch.setattr(
        bootstrap_runtime, "invalidate_model_cache", lambda: invalidated.append(True)
    )
    thread = bootstrap_runtime.ensure_essential_models_async()
    assert thread is not None
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert installed == list(bootstrap_runtime.ESSENTIAL_MODELS)
    assert invalidated

    jobs = [
        job
        for job in database.list_jobs()
        if job.get("origin") == "bootstrap"
    ]
    assert {job["model_id"] for job in jobs} == set(bootstrap_runtime.ESSENTIAL_MODELS)
    assert all(job["status"] == "succeeded" for job in jobs)
    assert all(job["stage"].startswith("downloading ") for job in jobs)
    assert all(job["progress"] == 100 for job in jobs)


def test_bootstrap_records_an_offline_failure_without_raising(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.delenv("VIDEOWFLOW_NO_AUTO_DOWNLOAD", raising=False)
    monkeypatch.setattr(bootstrap_runtime, "installed_path", lambda model_id: None)
    monkeypatch.setattr(
        bootstrap_runtime,
        "install_model",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("machine is offline")
        ),
    )
    thread = bootstrap_runtime.ensure_essential_models_async()
    assert thread is not None
    thread.join(timeout=5)
    jobs = [
        job
        for job in database.list_jobs()
        if job.get("origin") == "bootstrap"
    ]
    assert jobs
    assert all(job["status"] == "failed" for job in jobs)
    assert any("offline" in str(job.get("message")) for job in jobs)


def test_bootstrap_keeps_a_single_thread(monkeypatch) -> None:
    monkeypatch.delenv("VIDEOWFLOW_NO_AUTO_DOWNLOAD", raising=False)
    monkeypatch.setattr(bootstrap_runtime, "installed_path", lambda model_id: None)
    release = threading.Event()

    def slow_install(model_id, *, allow_network=True, progress=None):
        release.wait(timeout=5)
        return {"id": model_id, "installed": True}

    monkeypatch.setattr(bootstrap_runtime, "install_model", slow_install)
    first = bootstrap_runtime.ensure_essential_models_async()
    second = bootstrap_runtime.ensure_essential_models_async()
    assert first is second
    release.set()
    assert first is not None
    first.join(timeout=5)


def test_cli_without_a_command_uses_the_tray_when_available(monkeypatch) -> None:
    from videoflow import cli

    monkeypatch.setattr(tray, "tray_available", lambda: True)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        cli, "_tray", lambda args: captured.update(vars(args)) or 0
    )
    assert cli.main([]) == 0
    assert captured == {
        "host": "127.0.0.1",
        "port": 8765,
        "no_open": False,
        "check": False,
        "no_auto_download": False,
    }


def test_cli_without_a_command_stays_headless_without_a_tray(monkeypatch) -> None:
    from videoflow import cli

    monkeypatch.setattr(tray, "tray_available", lambda: False)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        cli, "_serve", lambda args: captured.update(vars(args)) or 0
    )
    assert cli.main([]) == 0
    assert captured["open"] is False
    assert captured["ui"] is True


def test_cli_no_auto_download_flag_is_propagated(monkeypatch) -> None:
    from videoflow import cli

    monkeypatch.setattr(tray, "tray_available", lambda: False)
    monkeypatch.setattr(cli, "_serve", lambda args: 0)
    assert cli.main(["--no-auto-download"]) == 0
    assert os.environ["VIDEOWFLOW_NO_AUTO_DOWNLOAD"] == "1"
    monkeypatch.delenv("VIDEOWFLOW_NO_AUTO_DOWNLOAD", raising=False)


def test_serve_falls_back_to_the_next_port_before_starting(
    tmp_path: Path, monkeypatch
) -> None:
    from videoflow import cli
    from videoflow.application import bootstrap_runtime as bootstrap
    from videoflow.application import settings as settings_module

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(cli, "ensure_home", lambda: tmp_path / "home")
    monkeypatch.setattr(cli, "probe_service", lambda host, port: None)
    monkeypatch.setattr(cli, "port_is_busy", lambda host, port: True)
    calls: list[tuple[str, int, int]] = []

    def fake_pick(host, port, span=100):
        calls.append((host, port, span))
        return 8766

    monkeypatch.setattr(cli, "pick_available_port", fake_pick)
    monkeypatch.setattr(bootstrap, "ensure_essential_models_async", lambda jobs=None: None)

    class FakeLock:
        def __init__(self, port):
            self.port = port

        def acquire(self):
            return True

        def release(self):
            return None

    captured: dict[str, object] = {}

    def fake_locked(args, uvicorn, create_http_app):
        captured.update(host=args.host, port=args.port)
        return 0

    monkeypatch.setattr(cli, "_InstanceLock", FakeLock)
    monkeypatch.setattr(cli, "_serve_locked", fake_locked)
    monkeypatch.setattr(
        settings_module,
        "load_settings",
        lambda: settings_module.AppSettings(),
    )
    assert cli.main(["serve"]) == 0
    assert calls and calls[0] == ("127.0.0.1", 8765, 100)
    assert captured == {"host": "127.0.0.1", "port": 8766}


def test_supervisor_asks_for_a_bindable_port_with_a_hundred_port_span(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    monkeypatch.setattr(tray, "probe_service", lambda *args, **kwargs: None)
    monkeypatch.setattr(tray, "port_is_busy", lambda *args, **kwargs: False)
    spans: list[int] = []

    def fake_pick(host, port, span=100):
        spans.append(span)
        return 9100

    monkeypatch.setattr(tray, "pick_available_port", fake_pick)

    class FakeServer:
        should_exit = False

        def run(self) -> None:
            return None

    supervisor = tray.ServerSupervisor(
        "127.0.0.1",
        8765,
        server_factory=lambda *args: FakeServer(),
        app_factory=lambda: SimpleNamespace(state=SimpleNamespace()),
    )
    assert supervisor.start() is True
    try:
        assert supervisor.port == 9100
        assert spans == [100]
    finally:
        supervisor.stop()


def test_restart_kills_the_old_pid_and_returns_when_health_is_ready(
    monkeypatch, capsys
) -> None:
    from videoflow import cli

    calls: dict[str, object] = {}
    monkeypatch.setattr(
        cli,
        "read_active_server",
        lambda: {"host": "127.0.0.1", "port": 8765, "pid": 4242},
    )
    monkeypatch.setattr(cli, "_read_pid", lambda path: {"pid": 4242})
    monkeypatch.setattr(cli, "_remove_pid", lambda path: None)
    monkeypatch.setattr(cli, "remove_active_server", lambda **kwargs: None)
    monkeypatch.setattr(cli, "process_alive", lambda pid: False)
    monkeypatch.setattr(cli, "pick_available_port", lambda host, port, span=100: 8765)
    monkeypatch.setattr(cli, "probe_service", lambda host, port: {"service": "videoflow"})

    def fake_terminate(pid, *, force=False, timeout=5.0):
        calls.setdefault("terminate", []).append((pid, force, timeout))
        return True

    class Process:
        pid = 777

        def poll(self):
            return None

    def fake_spawn(host, port, *, no_auto_download=False):
        calls["spawn"] = (host, port, no_auto_download)
        return Process()

    monkeypatch.setattr(cli, "terminate_pid", fake_terminate)
    monkeypatch.setattr(cli, "spawn_detached_server", fake_spawn)
    args = SimpleNamespace(host="127.0.0.1", port=8765, no_auto_download=False)
    assert cli._restart(args) == 0
    assert calls["terminate"] == [(4242, False, 5.0)]
    assert calls["spawn"] == ("127.0.0.1", 8765, False)
    assert "restarted at" in capsys.readouterr().out


def test_restart_force_kills_an_old_pid_that_ignores_the_graceful_stop(
    monkeypatch,
) -> None:
    from videoflow import cli

    calls: list[tuple[int, bool, float]] = []
    monkeypatch.setattr(cli, "read_active_server", lambda: {})
    monkeypatch.setattr(cli, "_read_pid", lambda path: {"pid": 5000})
    monkeypatch.setattr(cli, "_remove_pid", lambda path: None)
    monkeypatch.setattr(cli, "remove_active_server", lambda **kwargs: None)
    monkeypatch.setattr(cli, "process_alive", lambda pid: True)
    monkeypatch.setattr(cli, "pick_available_port", lambda host, port, span=100: port)
    monkeypatch.setattr(cli, "probe_service", lambda host, port: {"service": "videoflow"})
    monkeypatch.setattr(
        cli,
        "terminate_pid",
        lambda pid, *, force=False, timeout=5.0: calls.append((pid, force, timeout))
        or True,
    )
    monkeypatch.setattr(
        cli,
        "spawn_detached_server",
        lambda host, port, *, no_auto_download=False: SimpleNamespace(
            pid=900, poll=lambda: None
        ),
    )
    args = SimpleNamespace(host="127.0.0.1", port=8765, no_auto_download=True)
    assert cli._restart(args) == 0
    assert calls == [(5000, False, 5.0), (5000, True, 1.0)]
    assert os.environ["VIDEOWFLOW_NO_AUTO_DOWNLOAD"] == "1"
    monkeypatch.delenv("VIDEOWFLOW_NO_AUTO_DOWNLOAD", raising=False)


def test_smoke_environment_disables_auto_download(tmp_path: Path) -> None:
    from scripts import smoke_windows

    env = smoke_windows.clean_env(tmp_path)
    assert env["VIDEOWFLOW_NO_AUTO_DOWNLOAD"] == "1"


def test_smoke_detects_a_running_bootstrap_job(tmp_path: Path) -> None:
    from scripts import smoke_windows

    database.upsert_job(
        "bootstrap-silero-vad",
        {
            "job_id": "bootstrap-silero-vad",
            "origin": "bootstrap",
            "status": "running",
            "stage": "downloading silero-vad",
        },
        db_path_override=tmp_path / "videoflow.db",
    )
    with pytest.raises(smoke_windows.SmokeError):
        smoke_windows.check_auto_download_disabled(tmp_path)


def test_smoke_accepts_a_home_without_bootstrap_jobs(tmp_path: Path) -> None:
    from scripts import smoke_windows

    smoke_windows.check_auto_download_disabled(tmp_path)
    database.upsert_job(
        "bootstrap-silero-vad",
        {
            "job_id": "bootstrap-silero-vad",
            "origin": "bootstrap",
            "status": "succeeded",
            "stage": "downloading silero-vad",
        },
        db_path_override=tmp_path / "videoflow.db",
    )
    smoke_windows.check_auto_download_disabled(tmp_path)


def test_packaging_spec_contains_the_windows_oneclick_imports() -> None:
    spec = Path(__file__).resolve().parents[2] / "packaging" / "videoflow.spec"
    text = spec.read_text(encoding="utf-8")
    for name in (
        "pystray._win32",
        "PIL.Image",
        "PIL.ImageDraw",
        "videoflow.application.bootstrap_runtime",
        "videoflow.domains.audio.pcm_io",
    ):
        assert name in text
