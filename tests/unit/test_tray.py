from __future__ import annotations

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


def test_supervisor_refuses_a_port_it_cannot_free(home, monkeypatch) -> None:
    monkeypatch.setattr(
        tray, "probe_service", lambda *args, **kwargs: {"service": "videoflow"}
    )
    monkeypatch.setattr(
        tray, "stop_services_on_port", lambda *args, **kwargs: {"free": False}
    )
    supervisor, created = _supervisor()

    with pytest.raises(tray.TrayError):
        supervisor.start()

    assert created == []
    assert not (home / "server.pid").exists()


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

    assert actions.status_label() == "Status: stopped"
    actions.open_ui()

    assert supervisor.calls == ["start"]
    assert opened == [f"http://127.0.0.1:8765/?v={tray.__version__}"]
    assert actions.status_label() == "Status: running"

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
        "Open VideoFlow",
        "Start service",
        "Stop service",
        "Restart service",
        "Quit",
    ]
    start = next(item for item in items if item.text == "Start service")
    stop = next(item for item in items if item.text == "Stop service")
    assert start.kwargs["enabled"](None) is True
    assert stop.kwargs["enabled"](None) is False

    supervisor.running = True
    assert start.kwargs["enabled"](None) is False
    assert stop.kwargs["enabled"](None) is True
    status = next(item for item in items if callable(item.text))
    assert status.text(None) == "Status: running"


def test_tray_available_requires_a_display(monkeypatch) -> None:
    monkeypatch.setattr(tray.sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    assert tray.tray_available() is False


def test_cli_tray_falls_back_when_unavailable(
    monkeypatch, tmp_path, capsys
) -> None:
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
