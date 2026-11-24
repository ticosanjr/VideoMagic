from __future__ import annotations

import sys
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

from videoflow.application import tray


class FakeApp:
    def __init__(self) -> None:
        self.state = SimpleNamespace()


class FakeServer:
    def __init__(self, app: Any, host: str, port: int, log_level: str) -> None:
        self.app = app
        self.host = host
        self.port = port
        self.log_level = log_level
        self.should_exit = False
        self.started = threading.Event()
        self.finished = threading.Event()

    def run(self) -> None:
        self.started.set()
        while not self.should_exit:
            time.sleep(0.005)
        self.finished.set()


class BoomServer(FakeServer):
    def run(self) -> None:
        self.started.set()
        raise RuntimeError("boom")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    monkeypatch.setattr(tray, "probe_service", lambda *args, **kwargs: None)
    monkeypatch.setattr(tray, "port_is_busy", lambda *args, **kwargs: False)
    return tmp_path


def _supervisor(factory=FakeServer):
    created: list[FakeServer] = []

    def build(app, host, port, log_level):
        server = factory(app, host, port, log_level)
        created.append(server)
        return server

    supervisor = tray.ServerSupervisor(
        "127.0.0.1",
        8765,
        server_factory=build,
        app_factory=FakeApp,
    )
    return supervisor, created


def test_supervisor_start_stop_and_pid_file(home) -> None:
    supervisor, created = _supervisor()

    assert supervisor.running is False
    assert supervisor.start() is True
    assert created[0].started.wait(1.0)
    assert supervisor.running is True
    assert (home / "server.pid").is_file()
    assert supervisor.start() is False

    assert supervisor.stop() is True
    assert created[0].finished.wait(1.0)
    assert supervisor.running is False
    assert not (home / "server.pid").exists()
    assert supervisor.stop() is False


def test_supervisor_restart_replaces_the_server(home) -> None:
    supervisor, created = _supervisor()

    assert supervisor.start() is True
    assert supervisor.restart() is True
    assert len(created) == 2
    assert created[1].started.wait(1.0)
    assert supervisor.running is True
    assert supervisor.stop() is True


def test_supervisor_falls_back_when_a_port_cannot_be_freed(home, monkeypatch) -> None:
    monkeypatch.setattr(tray, "probe_service", lambda *args, **kwargs: {"service": "videoflow"})
    monkeypatch.setattr(tray, "stop_services_on_port", lambda *args, **kwargs: {"free": False})
    supervisor, created = _supervisor()

    assert supervisor.start() is True
    assert supervisor.port != 8765
    assert created
    assert (home / "server.pid").is_file()
    assert supervisor.stop() is True


def test_supervisor_keeps_tray_alive_when_the_server_thread_dies(home) -> None:
    supervisor, created = _supervisor(factory=BoomServer)

    assert supervisor.start() is True
    assert created[0].started.wait(1.0)
    deadline = time.monotonic() + 1.0
    while supervisor.running and time.monotonic() < deadline:
        time.sleep(0.005)

    assert supervisor.running is False
    assert "boom" in supervisor.last_error
    assert not (home / "server.pid").exists()
    assert supervisor.stop() is True


class RecordingSupervisor:
    url = "http://127.0.0.1:8765/"

    def __init__(self) -> None:
        self.running = False
        self.calls: list[str] = []

    def start(self) -> bool:
        self.calls.append("start")
        self.running = True
        return True

    def stop(self) -> bool:
        self.calls.append("stop")
        self.running = False
        return True

    def restart(self) -> bool:
        self.calls.append("restart")
        self.running = True
        return True


def test_actions_open_starts_the_service_and_opens_the_versioned_url() -> None:
    supervisor = RecordingSupervisor()
    opened: list[str] = []
    actions = tray.TrayActions(supervisor, opener=opened.append)

    assert actions.status_label() == "Service: stopped"
    actions.open_ui()

    assert supervisor.calls == ["start"]
    assert opened == [f"http://127.0.0.1:8765/?v={tray.__version__}"]
    assert actions.status_label() == "Service: running"

    actions.stop()
    actions.restart()
    assert supervisor.calls == ["start", "stop", "restart"]


class FakeItem:
    def __init__(self, text, action, **kwargs) -> None:
        self.text = text
        self.action = action
        self.kwargs = kwargs


class FakeMenu:
    SEPARATOR = object()

    def __init__(self, *items) -> None:
        self.items = items


def test_menu_exposes_lifecycle_actions_and_dynamic_status() -> None:
    fake_pystray = SimpleNamespace(Menu=FakeMenu, MenuItem=FakeItem)
    supervisor = RecordingSupervisor()
    actions = tray.TrayActions(supervisor)
    menu = tray._menu(fake_pystray, actions, lambda icon: icon.stop())

    items = [item for item in menu.items if isinstance(item, FakeItem)]
    labels = [item.text for item in items if isinstance(item.text, str)]
    assert labels == [
        f"VideoFlow {tray.__version__}",
        "Open VideoFlow",
        "Open runs",
        "Restart service",
        "Start service",
        "Stop service",
        "Pause all jobs",
        "Resume all jobs",
        "Cancel all jobs",
        "Quit VideoFlow",
    ]
    start = next(item for item in items if item.text == "Start service")
    stop = next(item for item in items if item.text == "Stop service")
    restart = next(item for item in items if item.text == "Restart service")
    version = next(item for item in items if item.text == f"VideoFlow {tray.__version__}")
    assert version.kwargs["enabled"] is False
    assert start.kwargs["enabled"](None) is True
    assert stop.kwargs["enabled"](None) is False
    assert "enabled" not in restart.kwargs

    supervisor.running = True
    assert start.kwargs["enabled"](None) is False
    assert stop.kwargs["enabled"](None) is True
    status = next(item for item in items if callable(item.text))
    jobs = [item for item in items if callable(item.text)]
    assert status.text(None) == "Service: running"
    assert jobs[1].text(None) == "Jobs: idle"
    pause = next(item for item in items if item.text == "Pause all jobs")
    resume = next(item for item in items if item.text == "Resume all jobs")
    cancel = next(item for item in items if item.text == "Cancel all jobs")
    actions.job_stats = {"running": 1, "queued": 1, "paused": 0, "waiting": 1, "total": 3}
    assert pause.kwargs["enabled"](None) is True
    assert resume.kwargs["enabled"](None) is False
    assert cancel.kwargs["enabled"](None) is True

    quit_item = next(item for item in items if item.text == "Quit VideoFlow")

    class Icon:
        stopped = False

        def stop(self) -> None:
            self.stopped = True

    icon = Icon()
    quit_item.action(icon, None)
    assert icon.stopped


def test_tray_available_requires_a_display(monkeypatch) -> None:
    monkeypatch.setattr(tray.sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    assert tray.tray_available() is False


def test_system_gi_path_is_temporary(monkeypatch) -> None:
    monkeypatch.setattr(tray.sys, "platform", "linux")
    monkeypatch.setattr(tray.sys, "path", list(tray.sys.path))
    monkeypatch.setattr(tray.os.path, "isdir", lambda path: True)

    with tray._system_gi_path():
        assert "/usr/lib/python3/dist-packages" in tray.sys.path
    assert "/usr/lib/python3/dist-packages" not in tray.sys.path


def test_pystray_backend_override_is_temporary(monkeypatch) -> None:
    from types import ModuleType

    module = ModuleType("pystray")
    monkeypatch.setitem(sys.modules, "pystray", module)
    monkeypatch.setenv("VIDEOWFLOW_TRAY_BACKEND", "xorg")

    assert tray._import_pystray() is module
    assert "PYSTRAY_BACKEND" not in tray.os.environ


def test_refresh_status_reports_running_and_unreachable(monkeypatch) -> None:
    supervisor = RecordingSupervisor()
    actions = tray.TrayActions(supervisor)
    supervisor.running = True

    monkeypatch.setattr(tray, "probe_service", lambda *args, **kwargs: {"ok": True})
    actions.refresh_status()
    assert actions.status_label() == "Service: running"

    monkeypatch.setattr(tray, "probe_service", lambda *args, **kwargs: None)
    actions.refresh_status()
    assert actions.status_label() == "Service: unreachable"

    supervisor.running = False
    actions.refresh_status()
    assert actions.status_label() == "Service: stopped"


def test_cli_tray_falls_back_when_unavailable(monkeypatch, tmp_path, capsys) -> None:
    from videoflow import cli

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    monkeypatch.setattr(tray, "tray_available", lambda: False)
    captured: dict[str, object] = {}

    def fake_serve(args):
        captured.update(vars(args))
        return 0

    monkeypatch.setattr(cli, "_serve", fake_serve)

    assert cli.main(["tray", "--no-open"]) == 0
    assert captured == {"host": "127.0.0.1", "port": 8765, "open": False}
    assert "tray backend" in capsys.readouterr().err.lower()


def test_cli_tray_passes_host_port_and_open(monkeypatch, tmp_path) -> None:
    from videoflow import cli

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    monkeypatch.setattr(tray, "tray_available", lambda: True)
    captured: dict[str, object] = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(tray, "run_tray", fake_run)

    assert cli.main(["tray", "--host", "0.0.0.0", "--port", "9000"]) == 0
    assert captured == {
        "host": "0.0.0.0",
        "port": 9000,
        "open_browser": True,
    }


def test_tray_helpers_and_icon(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(tray, "bundle_root", lambda: tmp_path)
    assert tray._ui_url("0.0.0.0", 9000) == "http://127.0.0.1:9000/"
    assert tray._browser_url("http://x/") == f"http://x/?v={tray.__version__}"
    calls = {"n": 0}

    def probe(*args, **kwargs):
        calls["n"] += 1
        return {"ok": True} if calls["n"] > 1 else None

    monkeypatch.setattr(tray, "probe_service", probe)
    assert tray._wait_for_service("127.0.0.1", 1, timeout=1) is True

    image = tray._icon_image()
    assert image.size == (64, 64)


def _fake_pystray(
    monkeypatch,
    *,
    icon_error: Exception | None = None,
    run_error: Exception | None = None,
):
    monkeypatch.setattr(tray.TrayActions, "refresh_jobs", lambda self: None)
    import sys
    from types import ModuleType

    class FakeItem:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class FakeMenu:
        SEPARATOR = object()

        def __init__(self, *items):
            self.items = items

    class FakeIcon:
        def __init__(self, *args, **kwargs):
            if icon_error:
                raise icon_error

        def run(self):
            if run_error:
                raise run_error

        def stop(self):
            return None

        def update_menu(self):
            return None

    module = ModuleType("pystray")
    module.Menu = FakeMenu  # type: ignore[attr-defined]
    module.MenuItem = FakeItem  # type: ignore[attr-defined]
    module.Icon = FakeIcon  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pystray", module)
    return module


def test_run_tray_without_backend(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pystray":
            raise ImportError("no tray")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert tray.run_tray(host="127.0.0.1", port=8765, open_browser=False) == 1


def test_run_tray_stops_when_start_fails(monkeypatch) -> None:
    _fake_pystray(monkeypatch)

    class Supervisor:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise tray.TrayError("port busy")

    monkeypatch.setattr(tray, "ServerSupervisor", Supervisor)
    assert tray.run_tray(host="127.0.0.1", port=8765, open_browser=False) == 1


def test_run_tray_icon_creation_failure(monkeypatch) -> None:
    _fake_pystray(monkeypatch, icon_error=RuntimeError("no desktop"))
    stopped: list[bool] = []

    class Supervisor:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            return True

        def stop(self):
            stopped.append(True)

    monkeypatch.setattr(tray, "ServerSupervisor", Supervisor)
    assert tray.run_tray(host="127.0.0.1", port=8765, open_browser=False) == 1
    assert stopped


def test_run_tray_backend_run_failure(monkeypatch) -> None:
    _fake_pystray(monkeypatch, run_error=RuntimeError("backend died"))
    stopped: list[bool] = []

    class Supervisor:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            return True

        def stop(self):
            stopped.append(True)

    monkeypatch.setattr(tray, "ServerSupervisor", Supervisor)
    assert tray.run_tray(host="127.0.0.1", port=8765, open_browser=False) == 1
    assert stopped


def test_run_tray_success_stops_the_supervisor(monkeypatch) -> None:
    _fake_pystray(monkeypatch)
    stopped: list[bool] = []

    class Supervisor:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            return True

        def stop(self):
            stopped.append(True)

    monkeypatch.setattr(tray, "ServerSupervisor", Supervisor)
    assert tray.run_tray(host="127.0.0.1", port=8765, open_browser=False) == 0
    assert stopped


def test_run_action_swallows_errors_and_updates(monkeypatch) -> None:
    calls: list[str] = []

    class Icon:
        def update_menu(self):
            calls.append("menu")

    tray._run_action(Icon(), lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert calls == ["menu"]


def test_server_factories_and_supervisor_url(home, monkeypatch) -> None:
    import uvicorn

    app = SimpleNamespace(state=SimpleNamespace())
    server = tray._uvicorn_server(app, "127.0.0.1", 1, "warning")
    assert isinstance(server, uvicorn.Server)
    assert tray._http_app() is not None

    supervisor, _ = _supervisor()
    assert supervisor.url == "http://127.0.0.1:8765/"
    monkeypatch.setattr(tray, "probe_service", lambda *args, **kwargs: None)
    assert tray._wait_for_service("127.0.0.1", 1, timeout=0.05) is False


def test_supervisor_start_thread_failure(home, monkeypatch) -> None:
    class BrokenThread:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def start(self) -> None:
            raise RuntimeError("cannot start")

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr(tray.threading, "Thread", BrokenThread)
    supervisor, _ = _supervisor()
    with pytest.raises(tray.TrayError, match="Could not start"):
        supervisor.start()
    assert supervisor.running is False
    assert not (home / "server.pid").exists()


def test_supervisor_stop_timeout_and_port_replacement(home, monkeypatch) -> None:
    class SlowServer:
        def __init__(self) -> None:
            self.should_exit = False

        def run(self) -> None:
            time.sleep(1.5)

    supervisor = tray.ServerSupervisor(
        "127.0.0.1",
        8765,
        server_factory=lambda *args: SlowServer(),
        app_factory=FakeApp,
    )
    assert supervisor.start() is True
    assert supervisor.stop(timeout=0.05) is True
    assert "did not stop" in supervisor.last_error

    monkeypatch.setattr(tray, "probe_service", lambda *args, **kwargs: None)
    monkeypatch.setattr(tray, "port_is_busy", lambda *args, **kwargs: True)
    monkeypatch.setattr(tray, "stop_services_on_port", lambda *args, **kwargs: {"free": True})
    supervisor._clear_port()


def test_actions_start_and_signal_handling(monkeypatch) -> None:
    supervisor = RecordingSupervisor()
    actions = tray.TrayActions(supervisor)
    actions.start()
    assert supervisor.calls == ["start"]

    calls: list[int] = []
    monkeypatch.setattr(tray.signal, "signal", lambda signum, handler: calls.append(signum))
    tray._install_signal_handlers(SimpleNamespace(stop=lambda: None))
    assert calls

    monkeypatch.setattr(
        tray.signal,
        "signal",
        lambda signum, handler: (_ for _ in ()).throw(ValueError("bad")),
    )
    tray._install_signal_handlers(SimpleNamespace(stop=lambda: None))


def test_tray_available_with_backend(monkeypatch) -> None:
    _fake_pystray(monkeypatch)
    monkeypatch.setattr(tray.sys, "platform", "win32")
    assert tray.tray_available() is True
    monkeypatch.setattr(tray.sys, "platform", "linux")
    monkeypatch.setenv("DISPLAY", ":0")
    assert tray.tray_available() is True


def test_run_tray_opens_the_browser_and_quits(monkeypatch) -> None:
    _fake_pystray(monkeypatch)
    opened: list[str] = []
    monkeypatch.setattr(tray.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(tray, "_wait_for_service", lambda *args, **kwargs: True)

    class Supervisor:
        running = True
        url = "http://127.0.0.1:8765/"

        def __init__(self, *args, **kwargs) -> None:
            pass

        def start(self) -> bool:
            return True

        def stop(self) -> bool:
            return True

    monkeypatch.setattr(tray, "ServerSupervisor", Supervisor)
    assert tray.run_tray(host="127.0.0.1", port=8765, open_browser=True) == 0
    assert opened


class FakeJobs:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.stats = {"running": 2, "queued": 1, "paused": 1, "waiting": 1, "total": 5}

    def snapshot(self):
        return dict(self.stats)

    def pause_all(self):
        self.calls.append("pause")
        self.stats = {"running": 0, "queued": 0, "paused": 3, "waiting": 1, "total": 5}
        return {"ok": True}

    def resume_all(self):
        self.calls.append("resume")
        self.stats = {"running": 2, "queued": 1, "paused": 0, "waiting": 1, "total": 5}
        return {"ok": True}

    def cancel_all(self):
        self.calls.append("cancel")
        self.stats = {"running": 0, "queued": 0, "paused": 0, "waiting": 0, "total": 0}
        return {"ok": True}


def test_actions_refresh_and_control_jobs() -> None:
    jobs = FakeJobs()
    opened: list[str] = []
    actions = tray.TrayActions(RecordingSupervisor(), opener=opened.append, jobs=jobs)
    actions.refresh_jobs()
    assert actions.jobs_label() == "Jobs: 2 running · 1 queued · 1 paused · 1 waiting"
    actions.pause_jobs()
    assert actions.jobs_label() == "Jobs: 3 paused · 1 waiting"
    actions.resume_jobs()
    assert "running" in actions.jobs_label()
    actions.cancel_jobs()
    assert actions.jobs_label() == "Jobs: idle"
    assert jobs.calls == ["pause", "resume", "cancel"]
    actions.open_runs()
    assert opened and opened[-1].endswith("#runs")


def test_job_controller_http(monkeypatch) -> None:
    calls: list[tuple[str, str, dict | None]] = []

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            if "/api/v1/jobs?" in calls[-1][1]:
                return {
                    "jobs": [
                        {"status": "running"},
                        {"status": "queued"},
                        {"status": "paused"},
                        {"status": "waiting_input"},
                        {"status": "succeeded"},
                    ]
                }
            return {"ok": True}

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method, url, json=None):
            calls.append((method, url, json))
            return Response()

    monkeypatch.setattr(tray.httpx, "Client", Client)
    controller = tray.TrayJobController("http://127.0.0.1:8765/")
    assert controller.snapshot() == {
        "running": 1,
        "queued": 1,
        "paused": 1,
        "waiting": 1,
        "total": 5,
    }
    controller.pause_all()
    controller.resume_all()
    controller.cancel_all()
    assert [item[1].split("/api/v1")[-1] for item in calls[1:]] == [
        "/jobs/pause_all",
        "/jobs/resume_all",
        "/jobs/cancel_all?force=true",
    ]


def test_tray_diagnostics_requires_a_menu_backend(monkeypatch) -> None:
    module = _fake_pystray(monkeypatch)
    monkeypatch.setattr(tray.sys, "platform", "win32")
    monkeypatch.setenv("DISPLAY", ":0")
    module.Icon.HAS_MENU = True

    diagnostics = tray.tray_diagnostics()
    assert diagnostics["available"] is True
    assert diagnostics["backend"]
    assert diagnostics["has_menu"] is True

    module.Icon.HAS_MENU = False
    diagnostics = tray.tray_diagnostics()
    assert diagnostics["available"] is False
    assert "no menu" in diagnostics["reason"]


def test_cli_tray_check_prints_diagnostics(monkeypatch, capsys) -> None:
    from videoflow import cli

    monkeypatch.setattr(
        tray,
        "tray_diagnostics",
        lambda: {
            "available": True,
            "backend": "pystray._appindicator",
            "has_menu": True,
            "reason": "",
        },
    )
    assert cli.main(["tray", "--check"]) == 0
    output = capsys.readouterr().out
    assert "pystray._appindicator" in output
    assert '"has_menu": true' in output
